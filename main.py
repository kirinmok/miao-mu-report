import os
import requests
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from dotenv import load_dotenv
from modules.role_analyzers import MultiRoleAnalyzer

# ==========================================
# 🐱 喵姆 AI 股市偵測站 v11.0 (決策型旗艦版)
# ==========================================

# 1. 載入設定
load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN")
YOUR_USER_ID = os.getenv("USER_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

class ProAnalyzer:
    @staticmethod
    def calculate_indicators(df):
        """ [內建數學核心] """
        df = df.sort_values('date')
        close = df['close']
        df['SMA_60'] = close.rolling(window=60).mean()
        
        # MACD
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def ask_perplexity(stock_name, stock_id, score, reasons, revenue_status, chip_status):
        """
        [未來透視鏡] 讓 AI 進行預測
        """
        if not PERPLEXITY_API_KEY:
            return "⚠️ 未設定 Perplexity API Key"

        print(f"🔮 AI 正在預測未來: {stock_name}...")
        
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = """
        你是一位視野前瞻的基金經理人。請不要只總結過去新聞。
        請根據使用者的數據，進行【未來 3-6 個月的趨勢預判】：
        1. 成長動能：該公司的產品線或產業趨勢，未來一季是看好還是看淡？
        2. 潛在風險：供應鏈、庫存或競爭對手有什麼隱憂？
        3. 操作建議：給出一個簡短的投資結論（積極佈局/區間操作/避開）。
        請用繁體中文，條列式回答，總字數控制在 150 字以內。
        """
        
        user_content = f"""
        股票：{stock_name} ({stock_id})
        目前評分：{score}/10
        技術訊號：{reasons}
        籌碼狀態：{chip_status}
        基本面狀態：{revenue_status}
        
        請預測未來的股價驅動力與風險。
        """

        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return f"❌ API Error: {response.status_code}"
        except Exception as e:
            return f"❌ 連線錯誤: {e}"

    @staticmethod
    def analyze_stock(dl, stock_id, stock_name):
        print(f"🚀 深度掃描: {stock_name} ({stock_id})...")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
            
            # 1. 抓取股價
            df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df.empty: return None
            df = ProAnalyzer.calculate_indicators(df)

            # 2. 籌碼分析 (外資 + 投信)
            df_chips = dl.taiwan_stock_institutional_investors(
                stock_id=stock_id, start_date=start_date, end_date=end_date
            )
            
            # 初始化變數
            foreign_net = 0
            trust_net = 0
            chip_msg = []
            chip_score = 0
            
            if not df_chips.empty:
                # 外資
                df_foreign = df_chips[df_chips['name'] == 'Foreign_Investor']
                if not df_foreign.empty:
                    last_5 = df_foreign.tail(5)
                    foreign_net = (last_5['buy'].sum() - last_5['sell'].sum()) // 1000
                    if foreign_net > 1000:
                        chip_msg.append("💰外資大買")
                        chip_score += 2.5
                    elif foreign_net < -1000:
                        chip_msg.append("💸外資提款")
                        chip_score -= 2.5
                
                # [升級模組 A] 內資雷達 (投信)
                df_trust = df_chips[df_chips['name'] == 'Investment_Trust']
                if not df_trust.empty:
                    last_5_t = df_trust.tail(5)
                    trust_net = (last_5_t['buy'].sum() - last_5_t['sell'].sum()) // 1000
                    if trust_net > 500: # 投信權重更高
                        chip_msg.append("🔥投信認養")
                        chip_score += 3.0
                    elif trust_net < -500:
                        chip_msg.append("📉投信棄養")
                        chip_score -= 3.0

            # 3. [升級模組 B] 基本面濾網 (月營收)
            revenue_msg = "營收持平"
            revenue_score = 0
            try:
                # 抓取較長區間以確保有資料
                rev_start = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
                df_rev = dl.taiwan_stock_month_revenue(
                    stock_id=stock_id, start_date=rev_start, end_date=end_date
                )
                if not df_rev.empty:
                    latest_rev = df_rev.iloc[-1]
                    yoy = latest_rev.get('revenue_year_growth', 0)
                    if yoy > 20:
                        revenue_msg = f"🚀營收爆發(+{yoy}%)"
                        revenue_score = 2.0
                    elif yoy < -20:
                        revenue_msg = f"⚠️營收衰退({yoy}%)"
                        revenue_score = -2.0
                    else:
                        revenue_msg = f"營收穩健({yoy}%)"
            except:
                pass

            # 4. 綜合評分
            latest = df.iloc[-1]
            close_price = latest['close']
            score = 5.0
            reasons = []
            
            # 加總分數
            score += chip_score
            score += revenue_score
            
            # 技術面評分
            ma60 = latest['SMA_60'] if not pd.isna(latest['SMA_60']) else close_price
            if close_price > ma60:
                score += 1.5
                reasons.append("📈站上季線")
            else:
                score -= 1.5
                reasons.append("📉跌破季線")

            macd = latest['MACD']
            signal = latest['MACD_signal']
            if macd > signal: reasons.append("🐂MACD金叉")
            else: reasons.append("🐻MACD死叉")
            
            rsi = latest['RSI_14']
            if rsi > 80: score -= 0.5; reasons.append("⚠️RSI過熱")
            elif rsi < 20: score += 1.0; reasons.append("💎RSI超賣")

            # 加入籌碼與營收理由
            reasons.extend(chip_msg)
            reasons.append(revenue_msg)

            score = max(1, min(10, score))
            
            # 建議
            if score >= 8.0: 
                rec = "🚀 強力買進"
                rec_class = "action-buy"
            elif score >= 6.5: 
                rec = "🔥 偏多操作"
                rec_class = "action-bullish"
            elif score <= 3.5: 
                rec = "⚠️ 建議賣出"
                rec_class = "action-sell"
            else: 
                rec = "⏸️ 觀望持有"
                rec_class = "action-hold"
            
            # 多角色分析 (保留 v10 功能)
            try:
                multi_role = MultiRoleAnalyzer()
                role_analysis = multi_role.analyze(
                    foreign_net_volume=int(foreign_net * 1000),
                    positive_days=3 if foreign_net > 0 else 0,
                    close=close_price, ma60=ma60, ma20=ma60, rsi=rsi,
                    macd_diff=macd - signal, price_change_5d=0,
                    has_positive_news=score>=7, has_negative_news=score<=3,
                    sector_trend="up", market_sentiment="neutral"
                )
            except:
                role_analysis = None

            return {
                '代號': stock_id, '名稱': stock_name, '收盤價': close_price,
                '評分': round(score, 1), '建議': rec, '建議類別': rec_class,
                '詳細理由': " ".join(reasons),
                '外資動向': f"{int(foreign_net)}張",
                '投信動向': f"{int(trust_net)}張",  # 新增
                '營收表現': revenue_msg,          # 新增
                '分析日期': end_date,
                'chart_data': {
                    'chips': min(100, max(0, 50 + int((foreign_net + trust_net)/20))),
                    'tech_ma': 80 if close_price > ma60 else 20,
                    'tech_macd': 80 if macd > signal else 20,
                    'tech_rsi': rsi,
                    'score': score * 10
                },
                'role_analysis': role_analysis
            }
        except Exception as e:
            print(f"❌ 分析錯誤: {e}")
            return None

def send_line_push(msg):
    if not LINE_CHANNEL_TOKEN or not YOUR_USER_ID: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}
    payload = {"to": YOUR_USER_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        requests.post(url, headers=headers, json=payload)
    except: pass

def main():
    print("\n🐱 啟動喵姆 AI 股市偵測站 v11.0 (決策型旗艦版)\n")
    
    # 預設清單
    my_portfolio = [
        ("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
        ("0056", "元大高股息"), ("00919", "群益高股息"),
        ("2603", "長榮"), ("2615", "萬海"), ("1519", "華城"),
        ("3293", "鈊象"), ("4763", "材料-KY"), ("2376", "技嘉"), ("2379", "瑞昱"),
        ("3034", "聯詠"), ("3035", "智原"), ("3680", "家登")
    ]
    
    # 嘗試讀取 JSON 清單
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
            print(f"📋 已載入追蹤清單：{len(my_portfolio)} 檔")
    except:
        print(f"⚠️ 使用預設清單：{len(my_portfolio)} 檔")

    dl = DataLoader()
    if FINMIND_TOKEN:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    
    excel_data = []
    line_msg = f"🐱 【股市報 v11.0】\n📅 {datetime.now().strftime('%Y-%m-%d')}\n"

    for stock_id, stock_name in my_portfolio:
        res = ProAnalyzer.analyze_stock(dl, stock_id, stock_name)
        if res:
            excel_data.append(res)
            
            # 觸發 AI 預測
            if res['評分'] >= 8 or res['評分'] <= 3:
                ai_res = ProAnalyzer.ask_perplexity(
                    stock_name, stock_id, res['評分'], res['詳細理由'], 
                    res['營收表現'], res['投信動向']
                )
                res['ai_insight'] = ai_res
                
                # 喵姆加分
                miao_score = res['評分']
                if "看好" in ai_res or "成長" in ai_res: miao_score += 1
                res['miao_score'] = min(10, miao_score)
                res['chart_data']['score'] = res['miao_score'] * 10
                
                # LINE 訊息
                icon = "🔥" if res['評分'] >= 8 else "💀"
                line_msg += f"\n{icon} {res['名稱']} ${res['收盤價']}\n"
                line_msg += f"評分:{res['miao_score']} | {res['營收表現']}\n"
                if "投信" in res['詳細理由']: line_msg += f"💡 {res['投信動向']} (投信介入)\n"
            
        time.sleep(1)

    # 生成網頁
    generate_index_html(excel_data)
    
    # LINE 發送
    line_msg += "\n👉 完整報表請看網頁版"
    print(line_msg)
    send_line_push(line_msg)
    
    # Excel 儲存
    try:
        df = pd.DataFrame(excel_data)
        if 'ai_insight' in df.columns: del df['ai_insight']
        if 'role_analysis' in df.columns: del df['role_analysis']
        if 'chart_data' in df.columns: del df['chart_data']
        df.to_excel(f"股市日報_v11_{datetime.now().strftime('%Y%m%d')}.xlsx", index=False)
        print("\n✅ Excel 報表已生成")
    except: pass

    # 自動開啟
    os.system("open index.html")

def generate_index_html(data):
    """ v11.0 新版網頁生成器：顯示投信與營收 """
    date_str = datetime.now().strftime('%Y-%m-%d')
    json_data = json.dumps(data, ensure_ascii=False)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 戰情室 v11.0</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: sans-serif; }}
            .card {{ background: #1e293b; border-radius: 16px; padding: 20px; border: 1px solid #334155; }}
            .badge {{ padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; margin-right: 5px; }}
            .bg-trust {{ background: #8b5cf6; color: white; }} /* 投信紫色 */
            .bg-rev-up {{ background: #ec4899; color: white; }} /* 營收粉紅 */
            .bg-rev-down {{ background: #64748b; color: white; }}
        </style>
    </head>
    <body class="p-6">
        <h1 class="text-3xl font-bold mb-2 text-center text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-400">
            🐱 喵姆 AI 戰情室 v11.0
        </h1>
        <p class="text-center text-gray-400 mb-8">決策型旗艦版 • {date_str}</p>
        
        <div id="container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto"></div>

        <script>
            const data = {json_data};
            const container = document.getElementById('container');
            
            data.forEach((item, idx) => {{
                // 判斷標籤顏色
                let trustBadge = '';
                if(item['投信動向'] && parseInt(item['投信動向']) > 0) {{
                    trustBadge = `<span class="badge bg-trust">🔥投信買超 ${{item['投信動向']}}</span>`;
                }} else if (item['投信動向'] && parseInt(item['投信動向']) < 0) {{
                     trustBadge = `<span class="badge bg-gray-600">📉投信賣超 ${{item['投信動向']}}</span>`;
                }}

                let revBadge = '';
                if(item['營收表現'].includes('爆發')) {{
                    revBadge = `<span class="badge bg-rev-up">${{item['營收表現']}}</span>`;
                }} else if(item['營收表現'].includes('衰退')) {{
                    revBadge = `<span class="badge bg-gray-600">${{item['營收表現']}}</span>`;
                }} else {{
                    revBadge = `<span class="badge bg-gray-700">${{item['營收表現']}}</span>`;
                }}

                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `
                    <div class="flex justify-between items-start mb-4">
                        <div>
                            <h2 class="text-xl font-bold text-white">${{item['名稱']}} <span class="text-gray-400 text-sm">${{item['代號']}}</span></h2>
                            <div class="text-2xl font-mono mt-1">$${{item['收盤價']}}</div>
                        </div>
                        <div class="text-right">
                            <div class="text-3xl font-bold ${{item['評分']>=8?'text-green-400':(item['評分']<=3?'text-red-400':'text-blue-400')}}">${{item['miao_score'] || item['評分']}}</div>
                            <div class="text-xs text-gray-500">喵姆評分</div>
                        </div>
                    </div>
                    
                    <div class="mb-4 space-y-2">
                        <div class="flex flex-wrap gap-2">
                            ${{item['建議'] ? `<span class="badge bg-blue-600">${{item['建議']}}</span>` : ''}}
                            ${{trustBadge}}
                            ${{revBadge}}
                        </div>
                    </div>

                    <div class="h-48 mb-4">
                        <canvas id="chart-${{idx}}"></canvas>
                    </div>
                    
                    ${{item.ai_insight ? `
                    <div class="p-3 bg-slate-800 rounded-lg border border-slate-700 text-sm text-gray-300">
                        <strong class="text-purple-400">🔮 AI 未來預測：</strong><br>
                        ${{item.ai_insight}}
                    </div>` : ''}}
                `;
                container.appendChild(card);

                // 畫圖
                new Chart(document.getElementById(`chart-${{idx}}`), {{
                    type: 'radar',
                    data: {{
                        labels: ['籌碼力', '季線', 'MACD', 'RSI', '綜合分'],
                        datasets: [{{
                            label: '數值',
                            data: [
                                item.chart_data.chips, 
                                item.chart_data.tech_ma,
                                item.chart_data.tech_macd,
                                item.chart_data.tech_rsi,
                                item.chart_data.score
                            ],
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.2)'
                        }}]
                    }},
                    options: {{
                        scales: {{ r: {{ suggestedMin: 0, suggestedMax: 100, grid: {{ color: '#334155' }} }} }},
                        plugins: {{ legend: {{ display: false }} }}
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ v11.0 戰情室網頁已生成")

if __name__ == "__main__":
    main()