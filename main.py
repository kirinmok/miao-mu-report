import os
import secrets
import requests
from flask import Flask, request, jsonify
import threading
import pandas as pd
import time
import json
import re
import traceback
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from dotenv import load_dotenv
from multiprocessing import Pool, cpu_count
from modules.role_analyzers import MultiRoleAnalyzer
import yfinance as yf
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import websocket
import backtrader as bt

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon')

import numpy as np

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NpEncoder, self).default(obj)

# ==========================================
# 🐱 喵姆 AI 股市偵測站 v14.0 (並行與安全強固版)
# ==========================================

load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN") or secrets.token_hex(16)
if not os.getenv("LINE_TOKEN"):
    print("⚠️ 未偵測到 LINE_TOKEN，生成臨時安全金鑰...")
YOUR_USER_ID = os.getenv("USER_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

app = Flask(__name__)

def parse_json_from_ai(content):
    """
    從 AI 回傳內容中提取並解析 JSON。
    """
    try:
        # 尋找 markdown 代碼塊
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # 尋找任何看起來像 JSON 的大括號內容
        json_match = re.search(r'(\{.*?\})', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ JSON 解析失敗: {e}")
        return None

def ai_supervisor(error_log, api_choice='perplexity'):
    """
    AI 自動監管模組（優先 Perplexity，若失敗則 Gemini）
    """
    prompt = f"你是一個專業的系統維運專家。請分析以下錯誤日誌，提供 JSON 格式的解決方案，包含 diagnosis (診斷) 與 actions (行動清單)。日誌：{error_log}"
    
    if api_choice == 'perplexity' and PERPLEXITY_API_KEY:
        try:
            url = "https://api.perplexity.ai/chat/completions"
            payload = {
                "model": "sonar-pro",
                "messages": [{"role": "user", "content": prompt}]
            }
            headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                result = parse_json_from_ai(content)
                return result if result else {'diagnosis': '解析失敗', 'actions': []}
            else:
                raise Exception(f"Perplexity API 錯誤: {response.text}")
        except Exception as e:
            print(f"⚠️ Perplexity 監管失敗: {e}. 嘗試 Gemini。")
            return ai_supervisor(error_log, 'gemini')
    
    elif api_choice == 'gemini' and os.getenv('GEMINI_API_KEY'):
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            content = response.text
            result = parse_json_from_ai(content)
            return result if result else {'diagnosis': '解碼失敗', 'actions': []}
        except Exception as e:
            print(f"⚠️ Gemini 監管失敗: {e}. 使用預設邏輯。")
            return {'diagnosis': '未知錯誤', 'actions': ['手動檢查網路', '等待 1 小時後重試']}
    
    return None

# --- Finnhub Webhook 處理器 ---
@app.route('/finnhub_webhook', methods=['POST'])
def handle_finnhub_webhook():
    # 步驟 1: 驗證身份
    provided_secret = request.headers.get('X-Finnhub-Secret')
    expected_secret = os.getenv('FINNHUB_WEBHOOK_SECRET')
    if not expected_secret or provided_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # 步驟 2: 立即確認事件
    payload = request.json
    response = jsonify({'status': 'Event received'})
    threading.Thread(target=process_event_background, args=(payload,)).start()
    return response, 200

def process_event_background(payload):
    # 步驟 3: 背景處理事件邏輯
    try:
        print(f"⚓ 處理 Finnhub 事件: {payload}")
        error_log = f"事件 payload: {json.dumps(payload, cls=NpEncoder)}"
        ai_result = ai_supervisor(error_log)
        if ai_result:
            print(f"🤖 AI 建議行動: {ai_result.get('actions', '無特定建議')}")
    except Exception as e:
        print(f"❌ 事件處理錯誤: {e}")

@app.route('/api/ask_ai', methods=['POST'])
def handle_ask_ai():
    data = request.json
    query = data.get('query')
    ticker = data.get('ticker')
    name = data.get('name')
    
    if not query:
        return jsonify({'error': 'Missing query'}), 400
        
    print(f"💬 AI 戰情室收到提問: {name} ({ticker}) - {query}")
    
    # 呼叫 Perplexity 或使用預設邏輯
    try:
        # 構造上下文供 AI 參考
        answer = ProAnalyzer.ask_perplexity_prediction(name, ticker, 5, "用戶手動提問", "N/A", "N/A", 0, additional_context=query)
        # 如果 Perplexity 沒開或失敗，回傳一個友善的訊息
        if not answer:
            answer = f"關於 {name} 的「{query}」，目前系統正在串接深度資料中。建議您可以先參考報告中的技術指標與籌碼動向。 (提示：請確保 PERPLEXITY_API_KEY 已正確設定)"
        
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin')
def admin_portal():
    # 讀取投資組合
    portfolio = {"cash_position": 0, "current_holdings": []}
    try:
        with open("portfolio.json", "r", encoding="utf-8") as f:
            portfolio = json.load(f)
    except: pass
    
    # 讀取最新分析數據
    analysis_data = []
    try:
        with open("daily_analysis.json", "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
    except: pass
    
    # 計算市值
    market_value = 0
    total_cost = 0
    holdings_detail = []
    for h in portfolio.get('current_holdings', []):
        current_price = 0
        for a in analysis_data:
            if a['代號'] == h['symbol']:
                current_price = a['收盤價']
                break
        mv = current_price * h['shares']
        cost_total = h['cost'] * h['shares']
        pnl = mv - cost_total
        pnl_pct = round(pnl / cost_total * 100, 2) if cost_total > 0 else 0
        market_value += mv
        total_cost += cost_total
        holdings_detail.append({
            'symbol': h['symbol'], 'name': h.get('name', h['symbol']),
            'shares': h['shares'], 'cost': h['cost'],
            'current_price': current_price, 'market_value': round(mv, 0),
            'pnl': round(pnl, 0), 'pnl_pct': pnl_pct
        })
    
    total_assets = portfolio['cash_position'] + market_value
    total_pnl = market_value - total_cost
    total_pnl_pct = round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0

    # 先產生持股清單 HTML
    holdings_rows = ""
    for h in holdings_detail:
        pnl_color = 'text-red-400' if h['pnl'] >= 0 else 'text-green-400'
        pnl_sign = '+' if h['pnl'] >= 0 else ''
        holdings_rows += f"""
        <tr class="border-b border-slate-800">
            <td class="py-3 font-medium">{h['symbol']} {h['name']}</td>
            <td class="py-3 text-right font-mono">{h['shares']}</td>
            <td class="py-3 text-right font-mono">${h['cost']}</td>
            <td class="py-3 text-right font-mono">${h['current_price']}</td>
            <td class="py-3 text-right font-mono">${h['market_value']:,.0f}</td>
            <td class="py-3 text-right font-mono {pnl_color}">
                {pnl_sign}{h['pnl']:,.0f} ({h['pnl_pct']}%)
            </td>
        </tr>
        """
    if not holdings_detail:
        holdings_rows = '<tr><td colspan="6" class="py-8 text-center text-slate-500">尚無持股資料</td></tr>'

    return f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 戰情室 - 管理後台</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: system-ui, sans-serif; }}
        </style>
    </head>
    <body class="p-6 max-w-4xl mx-auto">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-2xl font-bold text-cyan-400">⚙️ 喵姆 AI 管理後台</h1>
            <a href="/" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm">← 回主頁</a>
        </div>

        <!-- 資產總覽（只在這裡顯示） -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 p-5 rounded-2xl bg-slate-800/60 border border-slate-700">
            <div class="text-center">
                <p class="text-xs text-slate-400 mb-1">可用現金</p>
                <p class="text-xl font-mono text-emerald-400">${portfolio['cash_position']:,.0f}</p>
            </div>
            <div class="text-center">
                <p class="text-xs text-slate-400 mb-1">持股市值</p>
                <p class="text-xl font-mono text-cyan-400">${market_value:,.0f}</p>
            </div>
            <div class="text-center">
                <p class="text-xs text-slate-400 mb-1">總資產</p>
                <p class="text-xl font-mono text-white">${total_assets:,.0f}</p>
            </div>
            <div class="text-center">
                <p class="text-xs text-slate-400 mb-1">總盈虧</p>
                <p class="text-xl font-mono {'text-red-400' if total_pnl >= 0 else 'text-green-400'}">
                    {'+' if total_pnl >= 0 else ''}{total_pnl:,.0f} ({total_pnl_pct}%)
                </p>
            </div>
        </div>

        <!-- 持股明細 -->
        <div class="mb-8">
            <h2 class="text-lg font-bold text-white mb-4">📋 持股明細</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="text-left text-slate-400 border-b border-slate-700">
                            <th class="pb-3">股票</th>
                            <th class="pb-3 text-right">持股</th>
                            <th class="pb-3 text-right">成本價</th>
                            <th class="pb-3 text-right">現價</th>
                            <th class="pb-3 text-right">市值</th>
                            <th class="pb-3 text-right">損益</th>
                        </tr>
                    </thead>
                    <tbody>
                        {holdings_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 手動編輯持股 -->
        <div class="mb-8 p-5 rounded-2xl bg-slate-800/40 border border-slate-700">
            <h2 class="text-lg font-bold text-white mb-4">✏️ 編輯持股</h2>
            <p class="text-xs text-slate-400 mb-4">修改 portfolio.json 後重新執行 main.py 即可更新。格式範例：</p>
            <pre class="bg-black/40 p-4 rounded-lg text-xs text-green-400 overflow-x-auto">
{{
  "cash_position": 500000,
  "current_holdings": [
    {{"symbol": "2330", "name": "台積電", "shares": 1000, "cost": 580}},
    {{"symbol": "0050", "name": "元大台灣50", "shares": 500, "cost": 130}}
  ]
}}
            </pre>
            <p class="text-xs text-slate-500 mt-3">🔮 未來版本將支援 OCR 自動讀取券商庫存截圖</p>
        </div>

        <!-- AI 資產配置建議（預留） -->
        <div class="p-5 rounded-2xl bg-indigo-900/20 border border-indigo-500/30">
            <h2 class="text-lg font-bold text-indigo-400 mb-2">🤖 AI 資產配置建議</h2>
            <p class="text-sm text-slate-300">根據您的資產規模 and 持股狀況，系統建議：</p>
            <ul class="text-sm text-slate-300 mt-3 space-y-2">
                <li>💰 建議單一個股投入不超過總資產的 <span class="text-cyan-400 font-bold">15%</span>（約 ${total_assets * 0.15:,.0f}）</li>
                <li>🛡️ 建議保留至少 <span class="text-yellow-400 font-bold">20%</span> 現金作為緊急預備（目前現金佔比 {round(portfolio['cash_position'] / total_assets * 100, 1) if total_assets > 0 else 0}%）</li>
                <li>📊 目前持股集中度：{len(holdings_detail)} 檔，{'分散度尚可' if len(holdings_detail) >= 3 else '過度集中，建議分散'}</li>
            </ul>
        </div>

    </body>
    </html>
    """


def start_webhook_server():
    print("🚀 啟動 Webhook 監聽伺服器 (Port 5000)...")
    app.run(host='0.0.0.0', port=5000, debug=False)

# --- 多核心並行包裝器 ---
def process_stock_wrapper(args):
    stock_id, stock_name, api_token = args
    # 每個進程需要獨立的 DataLoader 以避免 Session 衝突
    try:
        dl_proc = DataLoader()
        if api_token: 
            dl_proc.login_by_token(api_token=api_token)
    except Exception as e:
        print(f"⚠️ 進程 {stock_id} 登入失敗: {e}")
        dl_proc = None
        
    try:
        # 預設支援 SMA_custom 以演示功能
        res = ProAnalyzer.analyze_stock(dl_proc, stock_id, stock_name, custom_indicators=['SMA_custom'])
        if res:
            # 只有評分極端時才進行深度 AI 分析，節省 API 額度
            if res['評分'] >= 8 or res['評分'] <= 3:
                chip_status = f"投信{res['投信動向']}張, 外資{res['外資動向']}張"
                ai_pred = ProAnalyzer.ask_perplexity_prediction(stock_name, stock_id, res['評分'], res['詳細理由'], res['營收表現'], chip_status, res['收盤價'])
                res['ai_insight'] = ai_pred
        return res
    except Exception as e:
        print(f"❌ 進程分析出錯 ({stock_id}): {e}")
        return None

# --- Backtrader 策略類別 ---
class MiauBacktestStrategy(bt.Strategy):
    params = (('sma_period', 60),)

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.sma = bt.indicators.SimpleMovingAverage(self.datas[0], period=self.params.sma_period)
        self.macd = bt.indicators.MACD(self.datas[0])
        self.rsi = bt.indicators.RSI(self.datas[0])
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            # 買進條件: 收盤價 > 季線 且 MACD 金叉 (MACD > Signal)
            if self.dataclose[0] > self.sma[0] and self.macd.macd[0] > self.macd.signal[0]:
                self.order = self.buy()
        else:
            # 賣出條件: 收盤價 < 季線 或 RSI 過熱 (> 80)
            if self.dataclose[0] < self.sma[0] or self.rsi[0] > 80:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None



class ProAnalyzer:
    @staticmethod
    def calculate_indicators(df, custom_indicators=None):
        df = df.sort_values('date')
        close = df['close']
        df['SMA_60'] = close.rolling(window=60).mean()
        
        # 增補：客製化指標 (SMA_custom = 30日均線)
        if custom_indicators and 'SMA_custom' in custom_indicators:
            df['SMA_custom'] = close.rolling(window=30).mean()
        
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        
        # Bollinger Bands (20, 2)
        df['SMA_20'] = close.rolling(window=20).mean()
        df['STD_20'] = close.rolling(window=20).std()
        df['BB_upper'] = df['SMA_20'] + 2 * df['STD_20']
        df['BB_lower'] = df['SMA_20'] - 2 * df['STD_20']
        
        # Stochastic Oscillator (KD) (9,3,3)
        low_min = df['min'].rolling(window=9).min()
        high_max = df['max'].rolling(window=9).max()
        rsv = 100 * ((df['close'] - low_min) / (high_max - low_min))
        df['Stoch_K'] = rsv.ewm(alpha=1/3, adjust=False).mean().fillna(50)

        delta = close.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        # 增補：計算Fibonacci回檔水平（基於最近高低點）
        price_max = df['close'].max()
        price_min = df['close'].min()
        diff = price_max - price_min
        df['Fib_236'] = price_max - 0.236 * diff
        df['Fib_382'] = price_max - 0.382 * diff
        df['Fib_500'] = price_max - 0.500 * diff
        df['Fib_618'] = price_max - 0.618 * diff
        df['Fib_786'] = price_max - 0.786 * diff
        return df

    @staticmethod
    def backtest_strategy(df, stock_name):
        """
        使用 Backtrader 進行歷史回測
        """
        if len(df) < 60:
            return {"total_return": 0, "win_rate": 0, "max_drawdown": 0}

        try:
            cerebro = bt.Cerebro()
            cerebro.addstrategy(MiauBacktestStrategy)

            # 轉換資料格式 (Pandas -> Backtrader)
            # 確保日期是 Index 且格式正確
            bt_df = df.copy()
            bt_df['date'] = pd.to_datetime(bt_df['date'])
            bt_df.set_index('date', inplace=True)
            
            # 對齊 yfinance 欄位名稱 (open, high, low, close, volume)
            # FinMind: open, max, min, close, Trading_Volume
            data_feed = bt.feeds.PandasData(
                dataname=bt_df,
                open='open',
                high='max',
                low='min',
                close='close',
                volume='Trading_Volume',
                plot=False
            )
            cerebro.adddata(data_feed)

            # 設定初始資金
            start_cash = 100000.0
            cerebro.broker.setcash(start_cash)
            # 設定手續費 (假設 0.1425%)
            cerebro.broker.setcommission(commission=0.001425)

            # 加入分析器
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

            results = cerebro.run()
            strat = results[0]

            # 提取回測指標
            final_value = cerebro.broker.getvalue()
            total_return = round((final_value - start_cash) / start_cash * 100, 2)
            
            dd = strat.analyzers.drawdown.get_analysis()
            max_dd = round(dd.max.drawdown, 2) if 'max' in dd else 0

            trade_info = strat.analyzers.trades.get_analysis()
            win_rate = 0
            if 'total' in trade_info and trade_info.total.closed > 0:
                win_rate = round(trade_info.won.total / trade_info.total.closed * 100, 2)

            print(f"📉 {stock_name} 回測完成: 報酬率 {total_return}%, 勝率 {win_rate}%, 最大回撤 {max_dd}%")
            
            return {
                "total_return": total_return,
                "win_rate": win_rate,
                "max_drawdown": max_dd,
                "final_value": round(final_value, 0)
            }
        except Exception as e:
            print(f"⚠️ {stock_name} 回測失敗: {e}")
            return {"total_return": 0, "win_rate": 0, "max_drawdown": 0}

    @staticmethod
    def ask_perplexity_prediction(stock_name, stock_id, score, reasons, revenue_status, chip_status, close_price, additional_context=None):
        if not PERPLEXITY_API_KEY: return None
        print(f"🔮 AI 正在進行深度分析: {stock_name}...")
        
        # 嘗試載入外部模板 (恢復專家整段分析)
        try:
            template_path = "templates/prompt_perplexity.txt"
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
                # 替換變數
                user_content = f"日期：{datetime.now().strftime('%Y-%m-%d')}\n標的：{stock_name} ({stock_id})\n收盤價：{close_price}\n技術摘要：{reasons} {chip_status} {revenue_status}"
                if additional_context:
                    user_content += f"\n額外上下文/提問：{additional_context}"
            else:
                # Fallback defined inline if file missing
                system_prompt = "你是一位專業的股市分析師，請針對該股票進行重點分析。"
                user_content = f"{stock_name} ({stock_id}) 評分:{score} 狀態:{reasons}"
                if additional_context:
                    user_content += f"\n用戶提問：{additional_context}"
        except Exception as e:
            print(f"⚠️ 模板載入失敗: {e}")
            return None

        url = "https://api.perplexity.ai/chat/completions"
        headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json={
                "model": "sonar-pro", 
                "messages": [
                    {"role": "system", "content": system_prompt}, 
                    {"role": "user", "content": user_content}
                ]
            }, headers=headers)
            
            if response.status_code == 200: 
                return response.json()['choices'][0]['message']['content']
            else:
                print(f"❌ API Error: {response.text}")
        except: pass
        return None

    @staticmethod
    def realtime_stream(stock_id, retry_count=0):
        """
        增補：多重管道 failover 機制，優先免費額度
        retry_count: 避免無限遞迴
        """
        if retry_count > 3:
            print(f"🛑 {stock_id} 已達最大重試次數，終止串流監控。")
            return

        print(f"📡 啟動 {stock_id} 即時行情串流 (管道重試: {retry_count})...")
        FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
        ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
        
        # 第一管道：Finnhub WebSocket (真正即時串流)
        finnhub_error = "未嘗試"
        if FINNHUB_API_KEY:
            try:
                def on_message(ws, message):
                    data = json.loads(message)
                    if data['type'] == 'update':
                        print(f"⚡ [Finnhub Real-time] {data['data']}")
                    else:
                        print(f"📡 [Finnhub] {data}")

                ws = websocket.WebSocketApp(f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}",
                                            on_message=on_message)
                ws.on_open = lambda ws: ws.send(json.dumps({'type':'subscribe', 'symbol': stock_id + '.TW'}))
                print("🔗 已連接至 Finnhub WebSocket...")
                ws.run_forever()
                return 
            except Exception as e:
                finnhub_error = str(e)
                print(f"⚠️ Finnhub 失敗: {e}. 跳轉下一個管道。")
        
        # 第二管道：Alpha Vantage (近實時輪詢)
        alpha_error = "未嘗試"
        if ALPHA_VANTAGE_API_KEY:
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={stock_id}.TW&apikey={ALPHA_VANTAGE_API_KEY}"
                print("📡 嘗試 Alpha Vantage 輪詢...")
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if "Global Quote" in data:
                        quote = data["Global Quote"]
                        print(f"🕒 [Alpha Vantage] 價格: {quote.get('05. price')} (更新時間: {quote.get('07. latest trading day')})")
                        for _ in range(60): # 限制輪詢次數或週期，避免無限阻塞
                            time.sleep(60)
                            try:
                                response = requests.get(url, timeout=10)
                                print(f"更新: {response.json().get('Global Quote', {}).get('05. price', 'N/A')}")
                            except:
                                break
                    else:
                        alpha_error = str(data)
                        print(f"⚠️ Alpha Vantage 資料格式錯誤: {data}")
                else:
                    alpha_error = f"HTTP {response.status_code}"
            except Exception as e:
                alpha_error = str(e)
                print(f"⚠️ Alpha Vantage 失敗: {e}. 跳轉下一個管道。")
        
        # 第三管道：Yahoo Finance (終極備援)
        yahoo_error = "未嘗試"
        try:
            print("📡 嘗試 Yahoo Finance 備援輪詢...")
            ticker = yf.Ticker(stock_id + ".TW")
            info = ticker.fast_info
            price = info.get('lastPrice') if info else None
            if price:
                print(f"🔄 [Yahoo Finance] 當前價: {price:.2f}")
                for _ in range(60):
                    time.sleep(60)
                    try:
                        price = ticker.fast_info.get('lastPrice')
                        if price: print(f"更新: {price}")
                    except:
                        break
            else:
                 yahoo_error = "No price data"
        except Exception as e:
            yahoo_error = str(e)
            print(f"❌ 所有即時管道均失敗: {e}")

        # 增補：AI 自動監管模組
        error_log = f"所有管道失敗。標的: {stock_id}, Finnhub: {finnhub_error}, Alpha: {alpha_error}, Yahoo: {yahoo_error}"
        ai_result = ai_supervisor(error_log)
        if ai_result:
            print(f"🤖 AI 診斷: {ai_result.get('diagnosis', '未知')}")
            for action in ai_result.get('actions', []):
                print(f"📌 AI 建議執行: {action}")
                if '增加延遲' in action:
                    print("🕒 執行中: 增加延遲 10 秒後重試...")
                    time.sleep(10)
                    ProAnalyzer.realtime_stream(stock_id, retry_count + 1) 
        else:
            print("無可用 AI 監管，使用預設重試。")
            time.sleep(300)
            ProAnalyzer.realtime_stream(stock_id, retry_count + 1)

    @staticmethod
    def analyze_stock(dl, stock_id, stock_name, custom_indicators=None):
        print(f"🚀 掃描中: {stock_name} ({stock_id})...")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
            
            
            
            try:
                df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            except Exception as e:
                print(f"⚠️ FinMind API Error: {e}")
                df = pd.DataFrame()
            
            # 增補：整合Yahoo Finance以支援全球股市 (若FinMind無資料)
            if df.empty:
                try:
                    print(f"🌍 FinMind 無資料，嘗試 Yahoo Finance: {stock_id}...")
                    # 台灣股票優先嘗試加 .TW
                    target_id = stock_id
                    if stock_id.isdigit(): target_id = stock_id + ".TW"
                    
                    yf_df = yf.download(target_id, start=start_date, end=end_date, progress=False, multi_level_index=False)
                    
                    # 若失敗且原 ID 非純數字 (例如美股)，則已嘗試過；若原 ID 為純數字但 .TW 失敗 (不太可能，除非下市)，則嘗試不加 .TW (防呆)
                    if yf_df.empty and not stock_id.isdigit():
                         pass # American stock failed
                    elif yf_df.empty and stock_id.isdigit():
                         # 備援：試試看如果不加 .TW (雖然機率低)
                         yf_df = yf.download(stock_id, start=start_date, end=end_date, progress=False, multi_level_index=False)

                    if not yf_df.empty:
                        yf_df.reset_index(inplace=True)
                        yf_cols = [c.lower() for c in yf_df.columns]
                        yf_df.columns = yf_cols
                        
                        # Mapping Yahoo(Title/Lower) to FinMind(Lower)
                        rename_map = {
                            'date': 'date', 'datetime': 'date',
                            'close': 'close', 'adj close': 'close',
                            'open': 'open',
                            'high': 'max', 
                            'low': 'min', 
                            'volume': 'Trading_Volume'
                        }
                        yf_df.rename(columns=rename_map, inplace=True)
                        
                        # Fallback for missing columns
                        if 'max' not in yf_df.columns and 'high' in yf_df.columns: yf_df.rename(columns={'high': 'max'}, inplace=True)
                        if 'min' not in yf_df.columns and 'low' in yf_df.columns: yf_df.rename(columns={'low': 'min'}, inplace=True)

                        for col in ['close', 'open', 'max', 'min', 'Trading_Volume']:
                            if col in yf_df.columns:
                                yf_df[col] = pd.to_numeric(yf_df[col], errors='coerce')
                        
                        # Ensure required columns exist
                        if 'close' in yf_df.columns and 'min' in yf_df.columns:
                             df = yf_df
                except Exception as e:
                    print(f"❌ Yahoo Finance 下載失敗: {e}")

            if df.empty: return None
            df = ProAnalyzer.calculate_indicators(df, custom_indicators=custom_indicators)

            # --- 籌碼分析 (外資+投信) ---
            try:
                df_chips = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
            except:
                df_chips = pd.DataFrame()
            
            foreign_net, trust_net = 0, 0
            chip_msg = []
            
            if not df_chips.empty:
                # 外資
                df_f = df_chips[df_chips['name'] == 'Foreign_Investor']
                if not df_f.empty: foreign_net = (df_f.tail(5)['buy'].sum() - df_f.tail(5)['sell'].sum()) // 1000
                # 投信
                df_t = df_chips[df_chips['name'] == 'Investment_Trust']
                if not df_t.empty: trust_net = (df_t.tail(5)['buy'].sum() - df_t.tail(5)['sell'].sum()) // 1000
                
                if trust_net > 500: chip_msg.append("🔥投信認養")
                elif trust_net < -500: chip_msg.append("📉投信棄養")
                if foreign_net > 1000: chip_msg.append("💰外資大買")
                elif foreign_net < -1000: chip_msg.append("💸外資提款")

            # --- 估值分析 (PE/PB/殖利率) ---
            pe_ratio, pb_ratio, dividend_yield = None, None, None
            valuation_msg = ""
            try:
                df_per = dl.taiwan_stock_per(stock_id=stock_id, start_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'), end_date=end_date)
                if not df_per.empty:
                    latest_per = df_per.iloc[-1]
                    pe_ratio = round(float(latest_per.get('PER', 0)), 1) if latest_per.get('PER', 0) else None
                    pb_ratio = round(float(latest_per.get('PBR', 0)), 2) if latest_per.get('PBR', 0) else None
                    dividend_yield = round(float(latest_per.get('dividend_yield', 0)), 2) if latest_per.get('dividend_yield', 0) else None
                    
                    if pe_ratio and pe_ratio > 0:
                        if pe_ratio > 30: valuation_msg = "⚠️本益比偏高"
                        elif pe_ratio < 12: valuation_msg = "💎本益比偏低"
                        else: valuation_msg = "📊本益比合理"
            except Exception as e:
                print(f"⚠️ 估值資料取得失敗 ({stock_id}): {e}")

            # --- 營收分析 ---
            revenue_msg = "營收持平"
            try:
                rev_start = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
                try:
                     df_rev = dl.taiwan_stock_month_revenue(stock_id=stock_id, start_date=rev_start, end_date=end_date)
                except:
                     df_rev = pd.DataFrame()

                if not df_rev.empty:
                    yoy = df_rev.iloc[-1].get('revenue_year_growth', 0)
                    if yoy > 20: revenue_msg = f"🚀營收爆發(+{yoy}%)"
                    elif yoy < -20: revenue_msg = f"⚠️營收衰退({yoy}%)"
            except: pass

            # --- 成交量分析 ---
            vol_msg = ""
            if 'Trading_Volume' in df.columns or 'Trading_money' in df.columns:
                vol_col = 'Trading_Volume' if 'Trading_Volume' in df.columns else 'Trading_money'
                recent_vol = df[vol_col].iloc[-1]
                avg_vol = df[vol_col].tail(20).mean()
                vol_ratio = round(recent_vol / avg_vol, 2) if avg_vol > 0 else 1.0
                if vol_ratio > 1.5:
                    vol_msg = f"🔊爆量({vol_ratio}倍)"
                elif vol_ratio < 0.5:
                    vol_msg = f"🔇量縮({vol_ratio}倍)"

            # --- 綜合評分 ---
            latest = df.iloc[-1]
            close = latest['close']
            prev_close = df.iloc[-2]['close'] if len(df) >= 2 else close
            change_pct = round((close - prev_close) / prev_close * 100, 2)
            score = 5.0
            reasons = []
            
            # --- 新聞情緒分析 ---
            try:
                stock_ticker = yf.Ticker(stock_id + ".TW")
                news = stock_ticker.news
                if news:
                    sia = SentimentIntensityAnalyzer()
                    sentiment_scores = [sia.polarity_scores(article['title'])['compound'] for article in news[:5]]
                    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
                    if avg_sentiment > 0.05: revenue_msg += " 😊正面情緒"
                    elif avg_sentiment < -0.05: revenue_msg += " 😔負面情緒"
            except Exception as e:
                pass

            score += max(-3.0, min(3.0, trust_net / 500))
            score += max(-2.5, min(2.5, foreign_net / 1000))
            score += 2.0 if "爆發" in revenue_msg else (-2.0 if "衰退" in revenue_msg else 0)
            
            if pe_ratio and pe_ratio > 0:
                if pe_ratio > 40: score -= 1.5
                elif pe_ratio > 30: score -= 0.5
                elif pe_ratio < 12: score += 1.0
            if valuation_msg:
                reasons.append(valuation_msg)
            
            # --- 技術指標判定 ---
            if close < latest['BB_lower']: reasons.append("⚠️觸及Bollinger下軌")
            elif close > latest['BB_upper']: reasons.append("🔥觸及Bollinger上軌")
            if latest['Stoch_K'] < 20: score += 1.0; reasons.append("💎Stochastic超賣")

            if abs(close - latest['Fib_618']) < close * 0.01: reasons.append("📍接近Fib 61.8%回檔")
            
            # 增補：產業基準比較（與S&P 500相關性）
            try:
                if 'date' in df.columns:
                    # 必須對齊日期
                    df_corr = df.set_index('date').sort_index()
                    df_corr.index = pd.to_datetime(df_corr.index)
                    
                    sp500 = yf.download("^GSPC", start=start_date, end=end_date, progress=False, multi_level_index=False)
                    if not sp500.empty:
                        sp500_close = sp500['Close']
                        # 合併計算相關性
                        aligned_df = pd.concat([df_corr['close'], sp500_close], axis=1, join='inner')
                        if not aligned_df.empty:
                            correlation = aligned_df.iloc[:, 0].corr(aligned_df.iloc[:, 1])
                            if correlation > 0.8: reasons.append("🌍高度相關S&P 500")
            except Exception as e:
                print(f"⚠️ S&P 500 Correlation Failed: {e}")

            ma60 = latest['SMA_60'] if not pd.isna(latest['SMA_60']) else close
            if close > ma60: score += 1.5; reasons.append("📈站上季線")
            else: score -= 1.5; reasons.append("📉跌破季線")

            macd, signal = latest['MACD'], latest['MACD_signal']
            if macd > signal: reasons.append("🐂MACD金叉")
            else: reasons.append("🐻MACD死叉")
            
            rsi = latest['RSI_14']
            if rsi > 80: score -= 0.5; reasons.append("⚠️過熱")
            elif rsi < 20: score += 1.0; reasons.append("💎超賣")

            reasons.extend(chip_msg)
            if vol_msg:
                reasons.append(vol_msg)
            score = max(1, min(10, score))
            
            if score >= 8: rec, rec_class = "🚀 強力買進", "action-buy"
            elif score >= 6.5: rec, rec_class = "🔥 偏多操作", "action-bullish"
            elif score <= 3.5: rec, rec_class = "⚠️ 建議賣出", "action-sell"
            else: rec, rec_class = "⏸️ 觀望持有", "action-hold"

            # --- 停損參考 ---
            stop_loss = round(ma60 * 0.97, 1)  # 季線下方 3%
            target_price = round(close * 1.10, 1)  # 目標報酬 10%
            risk_reward = round((target_price - close) / (close - stop_loss), 1) if close > stop_loss else 0

            # --- 多角色分析 ---
            role_analysis = None
            try:
                multi_role = MultiRoleAnalyzer()
                role_analysis = multi_role.analyze(
                    foreign_net_volume=int((foreign_net + trust_net) * 1000), 
                    positive_days=3 if foreign_net > 0 else 0,
                    close=close, ma60=ma60, ma20=ma60, rsi=rsi, macd_diff=macd-signal,
                    price_change_5d=0, has_positive_news=score>=7, has_negative_news=score<=3,
                    sector_trend="up", market_sentiment="neutral"
                )
            except: pass

            # --- Monte Carlo 模擬 (預測未來 100 日風險) ---
            var_95 = 0
            try:
                returns = df['close'].pct_change().dropna()
                if len(returns) > 20:
                    mean_return = returns.mean()
                    std_return = returns.std()
                    sims = 1000
                    time_horizon = 100
                    price_sims = np.zeros((sims, time_horizon))
                    price_sims[:, 0] = close
                    for t in range(1, time_horizon):
                        price_sims[:, t] = price_sims[:, t-1] * (1 + np.random.normal(mean_return, std_return, sims))
                    var_95 = float(np.percentile(price_sims[:, -1], 5))  # 95% VaR
                    if var_95 < close * 0.9: 
                        reasons.append("⚠️高風險 (Monte Carlo VaR)")
            except: pass
            
            # --- 歷史回測 ---
            backtest_results = ProAnalyzer.backtest_strategy(df, stock_name)

            # --- 白話決策摘要 ---
            summary_parts = []

            # 1. 趨勢方向
            if close > ma60:
                summary_parts.append(f"股價目前在季線（60日均線 ${round(ma60,1)}）之上，代表中期趨勢偏多")
            else:
                summary_parts.append(f"股價目前在季線（60日均線 ${round(ma60,1)}）之下，代表中期趨勢偏弱")

            # 2. 法人動態
            if trust_net > 500 or foreign_net > 1000:
                buyers = []
                if foreign_net > 1000: buyers.append(f"外資近5日買超 {abs(int(foreign_net))} 張")
                if trust_net > 500: buyers.append(f"投信買超 {abs(int(trust_net))} 張")
                summary_parts.append(f"法人積極進場（{'，'.join(buyers)}），代表專業機構看好")
            elif trust_net < -500 or foreign_net < -1000:
                sellers = []
                if foreign_net < -1000: sellers.append(f"外資賣超 {abs(int(foreign_net))} 張")
                if trust_net < -500: sellers.append(f"投信賣超 {abs(int(trust_net))} 張")
                summary_parts.append(f"法人正在撤退（{'，'.join(sellers)}），需留意賣壓")
            else:
                summary_parts.append("法人近期沒有明顯動作，籌碼面中性")

            # 3. 技術訊號（挑最重要的一個說）
            if macd > signal and close > ma60:
                summary_parts.append("技術指標 MACD 呈現金叉（短期動能向上），搭配站上季線，屬於偏多格局")
            elif macd < signal and close < ma60:
                summary_parts.append("技術指標 MACD 呈現死叉（短期動能向下），加上跌破季線，屬於偏空格局")
            elif macd > signal:
                summary_parts.append("MACD 出出現金叉，短線有反彈跡象，但尚未站上季線，仍需觀察")
            else:
                summary_parts.append("MACD 呈現死叉，短線動能偏弱")

            # 4. 成交量
            if vol_msg:
                if "爆量" in vol_msg:
                    summary_parts.append(f"今日成交量明顯放大（{vol_msg}），代表市場關注度提升，價格變動較具可信度")
                elif "量縮" in vol_msg:
                    summary_parts.append(f"今日成交量偏低（{vol_msg}），價格變動的可信度較低，建議觀望")

            # 4.5 估值狀態
            if pe_ratio and pe_ratio > 0:
                if pe_ratio > 30:
                    summary_parts.append(f"估值方面，目前本益比 {pe_ratio} 倍偏高，代表市場已經給了較高的期待，追高風險較大")
                elif pe_ratio < 12:
                    summary_parts.append(f"估值方面，目前本益比 {pe_ratio} 倍偏低，可能被市場低估，具有價值投資的潛力")
                else:
                    summary_parts.append(f"估值方面，目前本益比 {pe_ratio} 倍在合理範圍內")
                if dividend_yield and dividend_yield > 4:
                    summary_parts.append(f"殖利率 {dividend_yield}% 具有不錯的配息吸引力")

            # 5. 風控提醒
            if close > stop_loss:
                summary_parts.append(f"如果買進，建議設定停損在 ${stop_loss}（季線下方3%），目標價 ${target_price}，風險報酬比 {risk_reward}")
            else:
                summary_parts.append(f"⚠️ 目前股價已低於建議停損點 ${stop_loss}，風險較高")

            plain_summary = "。".join(summary_parts) + "。"

            return {
                '代號': stock_id, '名稱': stock_name, '收盤價': close,
                '漲跌幅': change_pct,
                '評分': round(score, 1), '建議': rec, '建議類別': rec_class,
                '詳細理由': " ".join(reasons),
                '白話摘要': plain_summary,
                '成交量狀態': vol_msg,
                '停損參考': stop_loss,
                '目標價': target_price,
                'risk_reward': risk_reward,
                'monte_carlo_var': var_95,
                'backtest': backtest_results,
                '本益比': pe_ratio,
                '股價淨值比': pb_ratio,
                '殖利率': dividend_yield,
                '估值狀態': valuation_msg,
                '投信動向': int(trust_net), '外資動向': int(foreign_net),
                '營收表現': revenue_msg, '分析日期': end_date,
                'chart_data': {
                    'chips': min(100, max(0, 50 + int((foreign_net+trust_net)/20))),
                    'tech_ma': 80 if close > ma60 else 20,
                    'tech_macd': 80 if macd > signal else 20,
                    'tech_rsi': rsi,
                    'score': score * 10
                },
                'role_analysis': role_analysis
            }
        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error: {e}")
            return None

def send_line_push(data):
    if not LINE_CHANNEL_TOKEN or not YOUR_USER_ID:
        print("❌ LINE Token 或 User ID 未設定，跳過通知")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"
    }

    # 1. 重點摘要
    summary_lines = []
    for i, stock in enumerate(data, 1):
        # emoji mapping based on recommendation
        icon = ""
        if "買進" in stock['建議']: icon = "🚀"
        elif "偏多" in stock['建議']: icon = "🔥"
        elif "賣出" in stock['建議']: icon = "⚠️"
        else: icon = "⏸️"
        
        # 簡化建議文字 (去掉前面的 emoji, 因為已經加在前面了)
        clean_rec = stock['建議'].split(' ')[-1] if ' ' in stock['建議'] else stock['建議']
        chg = stock.get('漲跌幅', 0)
        arrow = '▲' if chg >= 0 else '▼'
        summary_lines.append(f"{i}. {stock['名稱']} ${stock['收盤價']}({arrow}{abs(chg)}%): {icon} {clean_rec}")
    
    summary_text = "\n".join(summary_lines)
    
    # 2. 構建訊息
    # 找出最強和最弱的股票
    sorted_data = sorted(data, key=lambda x: x['評分'], reverse=True)
    top_pick = sorted_data[0] if sorted_data else None
    worst_pick = sorted_data[-1] if sorted_data else None

    highlight = ""
    if top_pick:
        highlight += f"\n\n🏆 今日最強：{top_pick['名稱']} (評分{top_pick['評分']}) → 停損參考 ${top_pick.get('停損參考', 'N/A')}"
    if worst_pick and worst_pick['評分'] <= 3:
        highlight += f"\n⚠️ 注意風險：{worst_pick['名稱']} (評分{worst_pick['評分']})"

    msg_text = f"🐱 喵姆 AI 戰情室 v14.0\n📅 {datetime.now().strftime('%Y-%m-%d')}\n\n📋 【重點速覽】\n{summary_text}{highlight}\n\n🔗 完整雷達與 AI 分析報告：\nhttps://kirinmok.github.io/miao-mu-report/"

    # 3. 詳細個股資訊 (選填，為了不洗版，可以只放前3名或重點股，或全部放同一則)
    # 這邊依照用戶需求，僅提供摘要與連結，讓介面更乾淨
    
    payload = {
        "to": YOUR_USER_ID,
        "messages": [
            {"type": "text", "text": msg_text}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            print("✅ LINE 通知已發送 (含重點摘要)")
        else:
            print(f"❌ LINE 發送失敗: {res.text}")
    except Exception as e:
        print(f"❌ LINE 發送錯誤: {e}")

def main():
    print("\n🐱 啟動喵姆 AI 股市偵測站 v14.0 (並行與安全強固版)\n")
    
    # 載入投資組合
    portfolio = {"cash_position": 0, "current_holdings": []}
    try:
        with open("portfolio.json", "r", encoding="utf-8") as f:
            portfolio = json.load(f)
            print(f"💰 載入投資組合: 現金 {portfolio['cash_position']}, 持股 {len(portfolio['current_holdings'])} 檔")
    except Exception as e:
        print(f"⚠️ 載入投資組合失敗: {e}")

    # 清單載入
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
    except:
        my_portfolio = [("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
                        ("0056", "元大高股息"), ("2603", "長榮"), ("1519", "華城"),
                        ("3293", "鈊象"), ("3035", "智原"), ("3680", "家登")]

    try:
        dl = DataLoader()
        if FINMIND_TOKEN: dl.login_by_token(api_token=FINMIND_TOKEN)
    except Exception as e:
        print(f"⚠️ FinMind Login Failed: {e}")
        dl = None
    
    excel_data = []
    
    # 準備並行運算參數
    tasks = [(stock_id, stock_name, FINMIND_TOKEN) for stock_id, stock_name in my_portfolio]
    
    print(f"🔥 啟動 {cpu_count()} 個並行核心進行分析...")
    
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(process_stock_wrapper, tasks)
    
    # 過濾失敗結果並存回 excel_data
    excel_data = [r for r in results if r is not None]

    print(f"✅ 完成 {len(excel_data)} 檔股票分析。")

    # 注入持股資訊
    holdings_map = {h['symbol']: h for h in portfolio.get('current_holdings', [])}
    for item in excel_data:
        h = holdings_map.get(item['代號'])
        if h:
            item['持股'] = h['shares']
            item['成本'] = h['cost']
            if h['shares'] > 0 and h['cost'] > 0:
                item['損益%'] = round((item['收盤價'] - h['cost']) / h['cost'] * 100, 2)
            else:
                item['損益%'] = 0
        else:
            item['持股'] = 0
            item['損益%'] = 0

    generate_index_html(excel_data, portfolio)
    send_line_push(excel_data)
    
    # [新增] 儲存數據給晚上的 AI 策略會議用
    try:
        with open("daily_analysis.json", "w", encoding="utf-8") as f:
            json.dump(excel_data, f, ensure_ascii=False, cls=NpEncoder, indent=2)
        print("✅ 數據已存檔 (daily_analysis.json)，準備進行晚間策略會議。")
    except Exception as e:
        print(f"❌ JSON 存檔失敗: {e}")

    # 增補：啟動 webhook 伺服器 (保持運行以供 AI 戰情室使用)
    server_thread = threading.Thread(target=start_webhook_server)
    server_thread.start()
    
    os.system("open index.html")
    print("\n💡 提示：分析完成並已開啟報告。後台伺服器運行中，您可以直接在網頁與 AI 戰情室對話。按 Ctrl+C 結束。")

def generate_index_html(data, portfolio=None):
    # --- 教育提示 (Tooltips) ---
    tooltips = {
        "RSI": "相對強弱指標，用來衡量股價超買或超賣的程度 (0-100)。",
        "MACD": "趨勢指標，透過快慢線的收斂與發散來判斷市場轉折。",
        "外資": "國際大型機構投資者，若連續買進通常代表看好台灣市場。",
        "投信": "國內投信基金，通常專注於中小型飆股分析。",
        "季線": "60 日移動平均線 (SMA-60)，是判斷股價中長期趨勢的關鍵生命線。"
    }
    
    # 處理數據中的關鍵字，加上 HTML title 屬性
    processed_data = []
    for item in data:
        new_item = item.copy()
        reason = new_item.get('詳細理由', '')
        for kw, tip in tooltips.items():
            if kw in reason:
                # 使用 HTML title 屬性實現懸停效果
                reason = reason.replace(kw, f'<span class="underline decoration-dotted cursor-help border-b border-gray-500" title="{tip}">{kw}</span>')
        new_item['詳細理由'] = reason
        processed_data.append(new_item)

    json_data = json.dumps(processed_data, ensure_ascii=False, cls=NpEncoder)
    
    today = datetime.now()
    weekdays = ["(一)", "(二)", "(三)", "(四)", "(五)", "(六)", "(日)"]
    date_str = f"{today.year}年{today.month}月{today.day}日 {weekdays[today.weekday()]}"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 戰情室 v14.0</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: 'Inter', system-ui, sans-serif; -webkit-font-smoothing: antialiased; padding-bottom: 2rem; }}
            .glass-card {{ background: rgba(30, 41, 59, 0.4); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; overflow: hidden; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.36); transition: transform 0.2s, box-shadow 0.2s; }}
            .glass-card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.45); border-color: rgba(255,255,255,0.15); }}
            
            .tab-btn {{ border-bottom: 2px solid transparent; color: #94a3b8; padding: 12px 16px; transition: all 0.2s; font-weight: 500; letter-spacing: 0.025em; width: 33.33%; }}
            .tab-btn:hover {{ color: #cbd5e1; background: rgba(255,255,255,0.03); }}
            .tab-btn.active {{ border-color: #38bdf8; color: #38bdf8; background: linear-gradient(to bottom, rgba(56, 189, 248, 0.1), transparent); }}
            
            .badge {{ padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.025em; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }}

            /* Action Buttons CSS */
            .action-btn {{ display: block; width: 100%; padding: 14px; border-radius: 12px; text-align: center; font-weight: 800; font-size: 1.25rem; margin-top: 15px; margin-bottom: 5px; box-shadow: 0 4px 15px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.2); text-shadow: 0 1px 2px rgba(0,0,0,0.3); transition: all 0.2s; letter-spacing: 0.05em; }}
            .action-btn:hover {{ transform: translateY(-2px); filter: brightness(110%); }}
            .action-btn:active {{ transform: translateY(0); filter: brightness(95%); }}
            
            .action-buy {{ background: linear-gradient(135deg, #059669, #047857); color: white; border: 1px solid #10b981; box-shadow: 0 0 20px rgba(16, 185, 129, 0.4); }}
            .action-sell {{ background: linear-gradient(135deg, #dc2626, #b91c1c); color: white; border: 1px solid #f87171; box-shadow: 0 0 20px rgba(239, 68, 68, 0.4); }}
            .action-hold {{ background: linear-gradient(135deg, #475569, #334155); color: #e2e8f0; border: 1px solid #64748b; }}
            .action-bullish {{ background: linear-gradient(135deg, #d97706, #b45309); color: white; border: 1px solid #fbbf24; }}
            
            /* AI Q&A Widget */
            .ai-input-box {{ background: rgba(0, 0, 0, 0.2); border: 1px solid rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 9999px; margin-top: 16px; display: flex; align-items: center; gap: 10px; transition: border-color 0.2s; }}
            .ai-input-box:focus-within {{ border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }}
            
            .ai-input {{ flex: 1; background: transparent; border: none; color: white; padding: 4px; font-size: 0.95rem; outline: none; }}
            .ai-input::placeholder {{ color: #64748b; }}
            
            .btn-ask {{ background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; padding: 6px 16px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; white-space: nowrap; box-shadow: 0 2px 10px rgba(59, 130, 246, 0.3); transition: all 0.2s; }}
            .btn-ask:hover {{ transform: scale(1.05); box-shadow: 0 4px 15px rgba(59, 130, 246, 0.5); }}
            .btn-ask:active {{ transform: scale(0.95); }}
            
            .loading-dots:after {{ content: '.'; animation: dots 1.5s steps(5, end) infinite; }}
            @keyframes dots {{ 0%, 20% {{ content: '.'; }} 40% {{ content: '..'; }} 60% {{ content: '...'; }} 80%, 100% {{ content: ''; }} }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <header class="text-center mb-10 relative">
            <!-- 右上角追蹤清單按鈕 -->
            <!-- 右上角追蹤清單按鈕 (已移除) -->

            <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-purple-400">🐱 喵姆 AI 戰情室 v14.0</h1>
            <p class="text-gray-400 text-sm mt-2">決策強化版 • 證據導向 • {date_str}</p>
            
            <!-- 頂部標籤群 -->
            <div class="mt-4 flex justify-center gap-3">
               <span class="px-4 py-2 rounded-full bg-cyan-900/30 text-cyan-400 text-sm border border-cyan-800/50">🎯 喵姆評分</span>
               <span class="px-4 py-2 rounded-full bg-purple-900/30 text-purple-400 text-sm border border-purple-800/50">🤖 Perplexity AI</span>
            </div>
            </div>
        </header>
        
        <div id="container" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 max-w-7xl mx-auto"></div>
        
        <!-- 管理後台按鈕 -->
        <a href="http://localhost:5000/admin" target="_blank" class="fixed bottom-6 left-6 bg-slate-700 hover:bg-slate-600 text-white p-4 rounded-full shadow-lg transition-all z-50 flex items-center gap-2 border border-slate-500">
            ⚙️ <span>管理後台</span>
        </a>

        <script>
            const data = {json_data};
            const container = document.getElementById('container');
            
            function switchTab(idx, tab) {{
                document.getElementById(`content-radar-${{idx}}`).classList.add('hidden');
                document.getElementById(`content-ai-${{idx}}`).classList.add('hidden');
                document.getElementById(`content-qa-${{idx}}`).classList.add('hidden');
                document.getElementById(`tab-radar-${{idx}}`).classList.remove('active');
                document.getElementById(`tab-ai-${{idx}}`).classList.remove('active');
                document.getElementById(`tab-qa-${{idx}}`).classList.remove('active');
                
                document.getElementById(`content-${{tab}}-${{idx}}`).classList.remove('hidden');
                document.getElementById(`tab-${{tab}}-${{idx}}`).classList.add('active');
            }}

            data.forEach((item, idx) => {{
                const price = Number(item['收盤價']).toFixed(2);
                // 籌碼證據字串 (給 AI 用)
                const chipEvidence = `外資近5日${{item['外資動向']>0?'買超':'賣超'}} ${{Math.abs(item['外資動向'])}} 張，投信${{item['投信動向']>0?'買超':'賣超'}} ${{Math.abs(item['投信動向'])}} 張`;
                
                // 頂部標籤
                let trustTag = item['投信動向'] > 0 ? `<span class="badge bg-purple-600 text-white">🔥投信+${{item['投信動向']}}</span>` : (item['投信動向'] < 0 ? `<span class="badge bg-gray-600 text-white">📉投信${{item['投信動向']}}</span>` : '');
                let revTag = item['營收表現'].includes('爆發') ? `<span class="badge bg-pink-500 text-white">${{item['營收表現']}}</span>` : `<span class="badge bg-gray-700 text-gray-300">${{item['營收表現']}}</span>`;
                let holdTag = '';

                const card = document.createElement('div');
                card.className = 'glass-card';
                card.innerHTML = `
                    <div class="p-5">
                        <div class="flex justify-between items-start">
                            <div>
                                <h2 class="text-xl font-bold text-white">${{item['名稱']}} <span class="text-sm text-gray-500">${{item['代號']}}</span></h2>
                                <div class="text-2xl font-mono mt-1 text-gray-200">
                                    $${{price}}
                                    <span class="text-sm ml-2 ${{item['漲跌幅']>=0?'text-red-400':'text-green-400'}}">
                                        ${{item['漲跌幅']>=0?'▲':'▼'}}${{Math.abs(item['漲跌幅'])}}%
                                    </span>
                                </div>
                                <div class="flex gap-2 mt-2 flex-wrap">${{trustTag}} ${{revTag}} ${{holdTag}}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-4xl font-bold ${{item['評分']>=8?'text-green-400':(item['評分']<=3?'text-red-400':'text-blue-400')}}">${{item['評分']}}</div>
                                <div class="text-xs text-gray-500 mt-1">喵姆評分</div>
                            </div>
                        </div>

                        <div class="action-btn ${{item['建議類別']}}">
                            ${{item['建議']}}
                        </div>

                        <div class="mx-5 mb-4 mt-2 p-4 rounded-xl bg-slate-800/60 border border-slate-700/50">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="text-sm font-bold text-cyan-400">💡 白話解讀</span>
                                <span class="text-xs text-slate-500">— 為什麼給這個建議？</span>
                            </div>
                            <p class="text-sm text-gray-300 leading-relaxed">${{item['白話摘要']}}</p>
                        </div>
                    </div>

                    <div class="flex border-t border-b border-gray-700/50 bg-slate-800/50">
                        <button onclick="switchTab(${{idx}}, 'radar')" id="tab-radar-${{idx}}" class="tab-btn active" style="width:33.3%">📊 雷達分析</button>
                        <button onclick="switchTab(${{idx}}, 'ai')" id="tab-ai-${{idx}}" class="tab-btn" style="width:33.3%">🤖 專家診斷</button>
                        <button onclick="switchTab(${{idx}}, 'qa')" id="tab-qa-${{idx}}" class="tab-btn" style="width:33.3%">💬 AI 戰情室</button>
                    </div>

                    <div class="p-5 h-80 overflow-y-auto bg-slate-900/30">
                        
                        <div id="content-qa-${{idx}}" class="hidden space-y-3">
                            <div class="p-3 bg-slate-800/30 rounded-lg text-center border border-dashed border-gray-700">
                                <p class="text-xs text-slate-400 mb-1">💡 讓 AI 分析師解決您的疑惑</p>
                                <div class="ai-input-box">
                                    <input type="text" id="ai-query-${{idx}}" class="ai-input" placeholder="問點什麼... (例如：分析競爭對手、檢查庫存)" onkeydown="if(event.keyCode===13) askAI(${{idx}}, '${{item['代號']}}', '${{item['名稱']}}')">
                                    <button class="btn-ask" onclick="askAI(${{idx}}, '${{item['代號']}}', '${{item['名稱']}}')">🚀 送出</button>
                                </div>
                            </div>
                            <div id="ai-response-container-${{idx}}" class="space-y-3">
                                <!-- AI responses will be loaded here -->
                            </div>
                        </div>

                        <div id="content-radar-${{idx}}">
                            <div class="h-48 mb-4 flex justify-center items-center">
                                <canvas id="chart-${{idx}}"></canvas>
                            </div>
                            <div class="bg-slate-800/80 p-3 rounded-lg border border-slate-700 space-y-2">
                                <div class="flex justify-between text-xs text-gray-300">
                                    <span>💰 外資動向</span>
                                    <span class="${{item['外資動向']>0?'text-red-400':'text-green-400'}} font-mono">${{item['外資動向']}} 張</span>
                                </div>
                                <div class="flex justify-between text-xs text-gray-300">
                                    <span>🏦 投信動向</span>
                                    <span class="${{item['投信動向']>0?'text-red-400':'text-green-400'}} font-mono">${{item['投信動向']}} 張</span>
                                </div>
                                ${{item['本益比'] ? `
                                <div class="pt-2 border-t border-slate-700 mt-2">
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span class="cursor-help" title="本益比 = 股價 ÷ 每股盈餘。越低代表越便宜，但也要看產業特性">📊 本益比(PE)</span>
                                        <span class="font-mono ${{item['本益比']>30?'text-red-400':item['本益比']<12?'text-green-400':'text-gray-200'}}">${{item['本益比']}}x</span>
                                    </div>
                                    ${{item['股價淨值比'] ? `
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span class="cursor-help" title="股價淨值比 = 股價 ÷ 每股淨值。低於 1 代表股價低於公司帳面價值">📗 淨值比(PB)</span>
                                        <span class="font-mono text-gray-200">${{item['股價淨值比']}}x</span>
                                    </div>
                                    ` : ''}}
                                    ${{item['殖利率'] ? `
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span class="cursor-help" title="殖利率 = 每年配息 ÷ 股價。越高代表每年領到的股息越多">💰 殖利率</span>
                                        <span class="font-mono ${{item['殖利率']>4?'text-green-400':'text-gray-200'}}">${{item['殖利率']}}%</span>
                                    </div>
                                    ` : ''}}
                                </div>
                                ` : ''}}
                                <div class="flex justify-between text-xs text-gray-300 pt-2 border-t border-slate-700 mt-2">
                                    <span>🛡️ 停損參考</span>
                                    <span class="text-yellow-400 font-mono">$${{item['停損參考']}}</span>
                                </div>
                                ${{item.monte_carlo_var > 0 ? `
                                <div class="flex justify-between text-xs text-gray-300">
                                    <span class="cursor-help" title="Monte Carlo 模擬：用 1000 次隨機模擬預測 100 天後的最差情境（95% 信心水準）">🎲 模擬最差價位(VaR)</span>
                                    <span class="font-mono text-orange-400">$${{Number(item.monte_carlo_var).toFixed(1)}}</span>
                                </div>
                                ` : ''}}
                                <div class="flex justify-between text-xs text-gray-300">
                                    <span>🎯 目標價</span>
                                    <span class="text-cyan-400 font-mono">$${{item['目標價']}}</span>
                                </div>
                                <div class="flex justify-between text-xs text-gray-300">
                                    <span>⚖️ 風報比</span>
                                    <span class="font-mono ${{item['風險報酬比']>=2?'text-green-400':'text-orange-400'}}">${{item['風險報酬比']}}</span>
                                </div>
                                ${{item.backtest && item.backtest.total_return !== 0 ? `
                                <div class="pt-2 border-t border-slate-700 mt-2">
                                    <div class="text-xs text-slate-400 mb-1">📉 歷史回測（近200日模擬）</div>
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span>模擬報酬率</span>
                                        <span class="font-mono ${{item.backtest.total_return>=0?'text-red-400':'text-green-400'}}">${{item.backtest.total_return}}%</span>
                                    </div>
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span>勝率</span>
                                        <span class="font-mono text-cyan-400">${{item.backtest.win_rate}}%</span>
                                    </div>
                                    <div class="flex justify-between text-xs text-gray-300">
                                        <span>最大回撤</span>
                                        <span class="font-mono text-yellow-400">${{item.backtest.max_drawdown}}%</span>
                                    </div>
                                </div>
                                ` : ''}}
                                <div class="text-xs text-gray-500 pt-2 border-t border-slate-700">
                                    💡 <span>${{item['詳細理由']}}</span>
                                </div>
                            </div>
                        </div>

                        <div id="content-ai-${{idx}}" class="hidden space-y-3">
                            ${{item.role_analysis ? `
                                <div class="space-y-3">
                                    ${{item.role_analysis.role_outputs.map(r => `
                                        <div class="bg-gray-800/80 p-3 rounded-lg border border-gray-700/50">
                                            <div class="flex justify-between items-center mb-1">
                                                <span class="text-sm font-bold text-gray-200">
                                                    ${{r.role_name === '籌碼分析官' ? '📊' : r.role_name === '技術分析官' ? '📉' : r.role_name === '情境分析官' ? '🌐' : '⚠️'}} ${{r.role_name}}
                                                </span>
                                                <span class="text-xs px-2 py-0.5 rounded ${{r.role_conclusion=='bullish'?'bg-green-900 text-green-400':r.role_conclusion=='bearish'?'bg-red-900 text-red-400':'bg-slate-700 text-slate-300'}}">
                                                    ${{r.role_conclusion=='bullish'?'看多':r.role_conclusion=='bearish'?'看空':'觀望'}}
                                                </span>
                                            </div>
                                            <ul class="text-xs text-gray-300 mt-2 pl-4 list-disc space-y-1">
                                                ${{r.key_evidence && r.key_evidence.length > 0 ? r.key_evidence.map(e => `<li>${{e}}</li>`).join('') : '<li class="text-gray-500">無顯著訊號</li>'}}
                                            </ul>
                                        </div>
                                    `).join('')}}
                                </div>
                            ` : '<p class="text-center text-gray-500 mt-10">數據不足</p>'}}

                            ${{item.ai_insight ? `
                                <div class="mt-4 p-3 bg-indigo-900/30 border border-indigo-500/30 rounded-lg">
                                    <p class="text-xs text-indigo-300 font-bold mb-1">🌍 國際戰情與事件分析 (AI 蒐證)</p>
                                    <p class="text-xs text-gray-300 leading-relaxed whitespace-pre-line">${{item.ai_insight}}</p>
                                </div>
                            ` : ''}}
                            
                            <!-- Perplexity 深度追蹤按鈕 -->
                            <a href="https://www.perplexity.ai/search?q=${{item['名稱']}} ${{item['代號']}} 股價走勢與風險分析" target="_blank" class="block w-full text-center py-3 rounded-lg bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white font-bold transition shadow-lg border border-purple-400/50 mt-4 flex items-center justify-center gap-2">
                                🔍 <span>前往 Perplexity 深度追蹤</span>
                            </a>
                        </div>
                    </div>
                `;
                container.appendChild(card);

                // Chart Logic
                new Chart(document.getElementById(`chart-${{idx}}`), {{
                    type: 'radar',
                    data: {{
                        labels: ['籌碼力', '趨勢力', '動能力(MACD)', '反轉力(RSI)', '綜合評分'],
                        datasets: [{{
                            data: [
                                item.chart_data.chips, 
                                item.chart_data.tech_ma, 
                                item.chart_data.tech_macd, 
                                item.chart_data.tech_rsi, 
                                item.chart_data.score
                            ],
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.25)',
                            borderWidth: 2,
                            pointRadius: 3,
                            pointBackgroundColor: '#38bdf8'
                        }}]
                    }},
                    options: {{
                        maintainAspectRatio: false,
                        scales: {{
                            r: {{
                                suggestedMin: 0, suggestedMax: 100,
                                ticks: {{ display: false }},
                                grid: {{ color: 'rgba(255,255,255,0.1)' }},
                                pointLabels: {{ color: '#94a3b8', font: {{ size: 10 }} }}
                            }}
                        }},
                        plugins: {{ legend: {{ display: false }} }}
                    }}
                }});
            }});

            async function askAI(idx, ticker, name) {{
                const queryInput = document.getElementById(`ai-query-${{idx}}`);
                const container = document.getElementById(`ai-response-container-${{idx}}`);
                const query = queryInput.value.trim();
                
                if (!query) return;
                
                // 1. 顯示 Loading
                const loadingId = `loading-${{Date.now()}}`;
                const loadingHtml = `
                    <div id="${{loadingId}}" class="bg-gray-800/80 p-3 rounded-lg border border-gray-700/50 animate-pulse">
                        <div class="flex items-center gap-2 text-sm text-gray-300">
                            <span>🤖</span> <span class="loading-dots">AI 正在分析數據中</span>
                        </div>
                        <div class="text-xs text-gray-500 mt-1 pl-6">"${{query}}"</div>
                    </div>
                `;
                container.insertAdjacentHTML('afterbegin', loadingHtml);
                queryInput.value = ''; // 清空輸入框
                
                // 2. 發送請求
                try {{
                    const res = await fetch('/api/ask_ai', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ query, ticker, name }})
                    }});
                    
                    const data = await res.json();
                    document.getElementById(loadingId).remove(); // 移除 Loading
                    
                    if (res.ok) {{
                        const resultHtml = `
                            <div class="bg-indigo-900/40 p-3 rounded-lg border border-indigo-500/30">
                                <div class="flex items-center gap-2 mb-2">
                                    <span class="text-indigo-400 font-bold text-sm">🤖 AI 回覆</span>
                                    <span class="text-xs text-gray-500 bg-slate-800 px-2 py-0.5 rounded">Q: ${{query}}</span>
                                </div>
                                <div class="text-xs text-gray-300 leading-relaxed whitespace-pre-line">${{data.answer}}</div>
                            </div>
                        `;
                        container.insertAdjacentHTML('afterbegin', resultHtml);
                    }} else {{
                        alert('❌ ' + data.error);
                    }}
                }} catch (e) {{
                    document.getElementById(loadingId).remove();
                    alert('❌ 連線錯誤');
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ v14.0 系統升級完成 (並行、安全與教育增強版)")

if __name__ == "__main__":
    main()