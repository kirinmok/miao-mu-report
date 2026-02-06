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
# 🐱 喵姆 AI 股市偵測站 v13.0 (視覺修正版)
# ==========================================

load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN")
YOUR_USER_ID = os.getenv("USER_ID")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

class ProAnalyzer:
    @staticmethod
    def calculate_indicators(df):
        df = df.sort_values('date')
        close = df['close']
        df['SMA_60'] = close.rolling(window=60).mean()
        
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def ask_perplexity_prediction(stock_name, stock_id, score, reasons, revenue_status, chip_status, close_price):
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
            else:
                # Fallback defined inline if file missing
                system_prompt = "你是一位專業的股市分析師，請針對該股票進行重點分析。"
                user_content = f"{stock_name} ({stock_id}) 評分:{score} 狀態:{reasons}"
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
    def analyze_stock(dl, stock_id, stock_name):
        print(f"🚀 掃描中: {stock_name} ({stock_id})...")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
            
            df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df.empty: return None
            df = ProAnalyzer.calculate_indicators(df)

            # --- 籌碼分析 (外資+投信) ---
            df_chips = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
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

            # --- 營收分析 ---
            revenue_msg = "營收持平"
            try:
                rev_start = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
                df_rev = dl.taiwan_stock_month_revenue(stock_id=stock_id, start_date=rev_start, end_date=end_date)
                if not df_rev.empty:
                    yoy = df_rev.iloc[-1].get('revenue_year_growth', 0)
                    if yoy > 20: revenue_msg = f"🚀營收爆發(+{yoy}%)"
                    elif yoy < -20: revenue_msg = f"⚠️營收衰退({yoy}%)"
            except: pass

            # --- 綜合評分 ---
            latest = df.iloc[-1]
            close = latest['close']
            score = 5.0
            reasons = []
            
            score += 3.0 if trust_net > 500 else (-3.0 if trust_net < -500 else 0)
            score += 2.5 if foreign_net > 1000 else (-2.5 if foreign_net < -1000 else 0)
            score += 2.0 if "爆發" in revenue_msg else (-2.0 if "衰退" in revenue_msg else 0)
            
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
            score = max(1, min(10, score))
            
            if score >= 8: rec, rec_class = "🚀 強力買進", "action-buy"
            elif score >= 6.5: rec, rec_class = "🔥 偏多操作", "action-bullish"
            elif score <= 3.5: rec, rec_class = "⚠️ 建議賣出", "action-sell"
            else: rec, rec_class = "⏸️ 觀望持有", "action-hold"

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

            return {
                '代號': stock_id, '名稱': stock_name, '收盤價': close,
                '評分': round(score, 1), '建議': rec, '建議類別': rec_class,
                '詳細理由': " ".join(reasons),
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
        summary_lines.append(f"{i}. {stock['名稱']}: {icon} {clean_rec}")
    
    summary_text = "\n".join(summary_lines)
    
    # 2. 構建訊息
    msg_text = f"🐱 喵姆 AI 戰情室 v13.0\n📅 {datetime.now().strftime('%Y-%m-%d')}\n\n📋 【重點速覽】\n{summary_text}\n\n🔗 完整雷達與 AI 分析報告：\nhttps://kirinmok.github.io/miao-mu-report/"

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
    print("\n🐱 啟動喵姆 AI 股市偵測站 v13.0 (視覺修正版)\n")
    
    # 清單載入
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
    except:
        my_portfolio = [("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
                        ("0056", "元大高股息"), ("2603", "長榮"), ("1519", "華城"),
                        ("3293", "鈊象"), ("3035", "智原"), ("3680", "家登")]

    dl = DataLoader()
    if FINMIND_TOKEN: dl.login_by_token(api_token=FINMIND_TOKEN)
    
    excel_data = []
    
    for stock_id, stock_name in my_portfolio:
        res = ProAnalyzer.analyze_stock(dl, stock_id, stock_name)
        if res:
            if res['評分'] >= 8 or res['評分'] <= 3:
                chip_status = f"投信{res['投信動向']}張, 外資{res['外資動向']}張"
                ai_pred = ProAnalyzer.ask_perplexity_prediction(stock_name, stock_id, res['評分'], res['詳細理由'], res['營收表現'], chip_status, res['收盤價'])
                res['ai_insight'] = ai_pred
            excel_data.append(res)
        time.sleep(3)

        time.sleep(3)

    generate_index_html(excel_data)
    send_line_push(excel_data)
    os.system("open index.html")

def generate_index_html(data):
    date_str = datetime.now().strftime('%Y-%m-%d')
    json_data = json.dumps(data, ensure_ascii=False)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 戰情室 v13.0</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: 'Noto Sans TC', sans-serif; }}
            .glass-card {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; overflow: hidden; }}
            .tab-btn {{ border-bottom: 2px solid transparent; color: #94a3b8; padding: 10px 16px; transition: all 0.3s; width: 50%; text-align: center; }}
            .tab-btn.active {{ border-color: #38bdf8; color: #38bdf8; background: rgba(56, 189, 248, 0.1); }}
            .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }}
            
            /* 行動建議按鈕特效 */
            .action-btn {{
                display: block; width: 100%; padding: 12px;
                border-radius: 12px; text-align: center; font-weight: bold; font-size: 1.25rem;
                margin-top: 15px; margin-bottom: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                transition: transform 0.2s;
            }}
            .action-btn:hover {{ transform: scale(1.02); }}
            .action-buy {{ background: linear-gradient(135deg, #10b981, #059669); color: white; border: 2px solid #34d399; box-shadow: 0 0 15px rgba(16, 185, 129, 0.5); }}
            .action-sell {{ background: linear-gradient(135deg, #ef4444, #dc2626); color: white; border: 2px solid #f87171; box-shadow: 0 0 15px rgba(239, 68, 68, 0.5); }}
            .action-hold {{ background: linear-gradient(135deg, #64748b, #475569); color: white; border: 2px solid #94a3b8; }}
            .action-bullish {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: white; border: 2px solid #fbbf24; }}
            
            /* WYSIWYG 編輯模式樣式 */
            .editable-active {{ border: 1px dashed #fbbf24; background: rgba(251, 191, 36, 0.1); cursor: text; }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <header class="text-center mb-10">
            <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-purple-400">🐱 喵姆 AI 戰情室 v13.0</h1>
            <p class="text-gray-400 text-sm mt-2">決策強化版 • 證據導向 • {{date_str}}</p>
        </header>
        
        <div id="container" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 max-w-7xl mx-auto"></div>
        
        <!-- 浮動編輯按鈕 -->
        <button onclick="toggleEditMode()" id="editBtn" class="fixed bottom-6 right-6 bg-indigo-600 hover:bg-indigo-500 text-white p-4 rounded-full shadow-lg transition-all z-50 flex items-center gap-2">
            ✏️ <span>進入編輯模式</span>
        </button>

        <script>
            const data = {json_data};
            const container = document.getElementById('container');
            let isEditMode = false;

            function toggleEditMode() {{
                isEditMode = !isEditMode;
                const btn = document.getElementById('editBtn');
                const editables = document.querySelectorAll('.editable-text');
                
                if (isEditMode) {{
                    btn.innerHTML = '💾 <span>退出並保存(本地)</span>';
                    btn.classList.add('bg-green-600');
                    btn.classList.remove('bg-indigo-600');
                    editables.forEach(el => {{
                        el.contentEditable = 'true';
                        el.classList.add('editable-active');
                    }});
                }} else {{
                    btn.innerHTML = '✏️ <span>進入編輯模式</span>';
                    btn.classList.remove('bg-green-600');
                    btn.classList.add('bg-indigo-600');
                    editables.forEach(el => {{
                        el.contentEditable = 'false';
                        el.classList.remove('editable-active');
                    }});
                    alert('你可以直接列印或截圖保存修改後的報告！');
                }}
            }}
            
            function switchTab(idx, tab) {{
                document.getElementById(`content-radar-${{idx}}`).classList.add('hidden');
                document.getElementById(`content-ai-${{idx}}`).classList.add('hidden');
                document.getElementById(`tab-radar-${{idx}}`).classList.remove('active');
                document.getElementById(`tab-ai-${{idx}}`).classList.remove('active');
                
                document.getElementById(`content-${{tab}}-${{idx}}`).classList.remove('hidden');
                document.getElementById(`tab-${{tab}}-${{idx}}`).classList.add('active');
            }}

            data.forEach((item, idx) => {{
                // 籌碼證據字串 (給 AI 用)
                const chipEvidence = `外資近5日${{item['外資動向']>0?'買超':'賣超'}} ${{Math.abs(item['外資動向'])}} 張，投信${{item['投信動向']>0?'買超':'賣超'}} ${{Math.abs(item['投信動向'])}} 張`;
                
                // 頂部標籤
                let trustTag = item['投信動向'] > 0 ? `<span class="badge bg-purple-600 text-white">🔥投信+${{item['投信動向']}}</span>` : (item['投信動向'] < 0 ? `<span class="badge bg-gray-600 text-white">📉投信${{item['投信動向']}}</span>` : '');
                let revTag = item['營收表現'].includes('爆發') ? `<span class="badge bg-pink-500 text-white">${{item['營收表現']}}</span>` : `<span class="badge bg-gray-700 text-gray-300">${{item['營收表現']}}</span>`;

                const card = document.createElement('div');
                card.className = 'glass-card';
                card.innerHTML = `
                    <div class="p-5">
                        <div class="flex justify-between items-start">
                            <div>
                                <h2 class="text-xl font-bold text-white">${{item['名稱']}} <span class="text-sm text-gray-500">${{item['代號']}}</span></h2>
                                <div class="text-2xl font-mono mt-1 text-gray-200">$${{item['收盤價']}}</div>
                                <div class="flex gap-2 mt-2 flex-wrap">${{trustTag}} ${{revTag}}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-4xl font-bold ${{item['評分']>=8?'text-green-400':(item['評分']<=3?'text-red-400':'text-blue-400')}}">${{item['評分']}}</div>
                                <div class="text-xs text-gray-500 mt-1">喵姆評分</div>
                            </div>
                        </div>

                        <div class="action-btn ${{item['建議類別']}}">
                            ${{item['建議']}}
                        </div>
                    </div>

                    <div class="flex border-t border-b border-gray-700/50 bg-slate-800/50">
                        <button onclick="switchTab(${{idx}}, 'radar')" id="tab-radar-${{idx}}" class="tab-btn active">📊 雷達分析</button>
                        <button onclick="switchTab(${{idx}}, 'ai')" id="tab-ai-${{idx}}" class="tab-btn">🤖 專家診斷</button>
                    </div>

                    <div class="p-5 h-80 overflow-y-auto bg-slate-900/30">
                        
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
                                <div class="text-xs text-gray-500 pt-2 border-t border-slate-700">
                                    💡 <span class="editable-text">${{item['詳細理由']}}</span>
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
                                                    ${{r.role_name === '籌碼分析官' ? '📊' : r.role_name === '技術分析官' ? '📉' : '⚠️'}} ${{r.role_name}}
                                                </span>
                                                <span class="text-xs px-2 py-0.5 rounded ${{r.role_conclusion=='bullish'?'bg-green-900 text-green-400':'bg-red-900 text-red-400'}}">
                                                    ${{r.role_conclusion=='bullish'?'看多':'看空'}}
                                                </span>
                                            </div>
                                            <div class="text-xs text-gray-400 mt-1 pl-1 border-l-2 border-gray-600 editable-text">
                                                ${{r.role_name === '籌碼分析官' ? chipEvidence : (r.key_evidence && r.key_evidence.length > 0 ? r.key_evidence[0] : '無顯著訊號')}}
                                            </div>
                                        </div>
                                    `).join('')}}
                                </div>
                            ` : '<p class="text-center text-gray-500 mt-10">數據不足</p>'}}

                            ${{item.ai_insight ? `
                                <div class="mt-4 p-3 bg-indigo-900/30 border border-indigo-500/30 rounded-lg">
                                    <p class="text-xs text-indigo-300 font-bold mb-1">🌍 國際戰情與事件分析 (AI 蒐證)</p>
                                    <p class="text-xs text-gray-300 leading-relaxed editable-text whitespace-pre-line">${item.ai_insight}</p>
                                </div>
                            ` : ''}}
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
        </script>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ v13.0 介面優化完成 (雷達圖修復 + AI 證據補完)")

if __name__ == "__main__":
    main()