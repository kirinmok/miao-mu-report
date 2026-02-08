import os
import requests
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from dotenv import load_dotenv

# ==========================================
# 喵姆 AI 股市偵測站 v10.0 (Perplexity 整合版)
# ==========================================

# 1. 載入設定
load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN")
YOUR_USER_ID = os.getenv("USER_ID") # 注意：.env 裡是用 USER_ID，但程式碼裡變數可能有異，這裡統一用 config
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

from modules.analyzer import analyze_stock

# ... (Previous imports remain)

# Remove ProAnalyzer class (it's now in modules/analyzer.py)

def send_line_push(msg):
    # ... (Keep existing implementation)
    if not LINE_CHANNEL_TOKEN or not YOUR_USER_ID:
        print("⚠️ 未設定 LINE Token 或 User ID，跳過發送")
        return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}
    payload = {"to": YOUR_USER_ID, "messages": [{"type": "text", "text": msg}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("✅ LINE 通知已成功發送！")
        else:
            print(f"❌ LINE 發送失敗 (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")

def main():
    print("\n🐱 啟動喵姆 AI 股市偵測站 v11.0 (Real-Time Core)\n")
    
    # ... (Keep existing loading logic)
    # Debug Check
    if not PERPLEXITY_API_KEY:
        print(f"⚠️ 警告: 讀取到的 PERPLEXITY_API_KEY 為空！請檢查 .env 檔案。")
    else:
        masked_key = PERPLEXITY_API_KEY[:4] + "***" + PERPLEXITY_API_KEY[-4:] if len(PERPLEXITY_API_KEY) > 8 else "***"
        print(f"✅ 成功讀取 API Key (長度: {len(PERPLEXITY_API_KEY)}): {masked_key}")

    # 載入追蹤清單
    watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    if os.path.exists(watchlist_path):
        try:
            with open(watchlist_path, "r", encoding="utf-8") as f:
                watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
            print(f"📋 已載入追蹤清單：{len(my_portfolio)} 檔股票")
        except Exception as e:
            print(f"⚠️ 讀取 watchlist.json 失敗: {e}，使用預設清單")
            my_portfolio = [("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50")]
    else:
        print("⚠️ 找不到 watchlist.json，使用預設清單")
        my_portfolio = [("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50")]
    
    excel_data = []
    line_msg = f"🐱 【喵姆 AI 股市偵測站】\n📅 {datetime.now().strftime('%Y-%m-%d')}\n基於多維度指標與 AI 調研的自動化決策系統\n"
    buffer_content = "你現在是頂尖分析師，請針對以下資料進行跨維度的批判性分析，找出潛在漏洞。\n\n"
    
    # 初始化 DataLoader
    dl = DataLoader()
    if FINMIND_TOKEN and len(FINMIND_TOKEN) > 50:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    else:
        print("⚠️ 使用訪客權限抓取資料")

    for stock_id, stock_name in my_portfolio:
        # 使用新模組 analyze_stock
        res = analyze_stock(dl, stock_id, stock_name, PERPLEXITY_API_KEY)
        if res:
            excel_data.append(res)
            
            # Line Message Logic (Simplified for brevity, logic remains same)
            if res['評分'] >= 8 or res['評分'] <= 3:
                icon = "🔥" if res['評分'] >= 8 else "💀"
                miao_score = res.get('miao_score', res['評分'])
                line_msg += f"\n{'='*18}\n{icon} {res['名稱']}({res['代號']}) ${res['收盤價']}\n"
                line_msg += f"🐱 喵姆評分: {miao_score}\n🤖 AI觀點: {res.get('ai_insight','')}\n"
                
                buffer_content += f"【{stock_name}】喵姆評分:{miao_score}\nAI:{res.get('ai_insight','')}\n{'-'*50}\n"
                
        time.sleep(1)

    # 寫入 Buffer
    try:
        with open("Transfer_to_AI.txt", "w", encoding="utf-8") as f:
            f.write(buffer_content)
    except: pass

    # 產生並開啟 HTML
    index_html_path = os.path.abspath("index.html")
    generate_index_html(excel_data) # Pass data to generator
    print(f"🚀 自動開啟戰情室: {index_html_path}")
    # os.system(f"open '{index_html_path}'") # Optional: let user open it via server
    
    # send_line_push(line_msg) # Optional based on config

def generate_index_html(data):
    date_str = datetime.now().strftime('%Y-%m-%d')
    json_data = json.dumps(data, ensure_ascii=False)
    
    # HTML Template with SERVER MODE support
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 戰情室 (v11.0)</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Space+Grotesk:wght@300;400;500;700&display=swap" rel="stylesheet">
        <!-- Styles omitted for brevity, assume previous styles exist -->
        <style>
            :root {{ --bg-primary: #0a0e1a; --bg-card: rgba(20, 30, 50, 0.85); --accent-cyan: #38bdf8; --accent-purple: #a855f7; }}
            body {{ background: linear-gradient(135deg, var(--bg-primary) 0%, #1a1a2e 50%, #16213e 100%); color: #e2e8f0; font-family: 'Noto Sans TC', sans-serif; min-height: 100vh; }}
            .glass-card {{ background: var(--bg-card); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); transition: all 0.3s ease; }}
            .action-badge {{ display: inline-block; padding: 6px 16px; border-radius: 9999px; font-weight: 700; font-size: 0.875rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
            .action-buy {{ background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.3); animation: pulse-red 2s infinite; }}
            .action-bullish {{ background: linear-gradient(135deg, #f97316, #ea580c); color: white; }}
            .action-hold {{ background: linear-gradient(135deg, #64748b, #475569); color: #e2e8f0; border: 1px solid rgba(255,255,255,0.1); }}
            .action-sell {{ background: linear-gradient(135deg, #22c55e, #15803d); color: white; }}
            .score-h {{ color: #f87171; text-shadow: 0 0 10px rgba(248, 113, 113, 0.5); }}
            .score-m {{ color: #fbbf24; }}
            .score-l {{ color: #4ade80; }}
            @keyframes pulse-red {{ 0% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }} 70% {{ box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }} 100% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }} }}
            .sidebar {{ position: fixed; right: 0; top: 0; width: 320px; height: 100vh; background: rgba(15, 23, 42, 0.98); border-left: 1px solid rgba(255,255,255,0.1); transform: translateX(100%); transition: transform 0.3s ease; z-index: 1000; overflow-y: auto; padding: 1.5rem; }}
            .sidebar.open {{ transform: translateX(0); }}
            .sidebar-toggle {{ position: fixed; right: 20px; top: 20px; z-index: 1001; background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple)); border: none; border-radius: 12px; padding: 12px 20px; color: white; font-weight: 600; cursor: pointer; }}
            .watchlist-input {{ width: 100%; padding: 12px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: white; margin-bottom: 10px; }}
            .watchlist-btn {{ width: 100%; padding: 12px; background: linear-gradient(135deg, #10b981, #059669); border: none; border-radius: 8px; color: white; font-weight: 600; cursor: pointer; margin-bottom: 20px; }}
            .loader {{ border: 3px solid rgba(255,255,255,0.1); border-radius: 50%; border-top: 3px solid #38bdf8; width: 24px; height: 24px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <header class="mb-12 flex flex-col md:flex-row items-center md:items-end gap-6">
                <div>
                    <h1 class="text-4xl font-bold mb-2" style="background: linear-gradient(135deg, #38bdf8, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">🐱 喵姆 AI 戰情室</h1>
                    <p class="text-gray-400">Real-Time AI Investment Strategy • {date_str}</p>
                </div>
                <div class="flex gap-3 md:mb-1">
                   <span class="px-4 py-2 rounded-full bg-cyan-900/30 text-cyan-400 text-sm border border-cyan-800/50">🎯 喵姆評分</span>
                   <span class="px-4 py-2 rounded-full bg-purple-900/30 text-purple-400 text-sm border border-purple-800/50">🤖 Perplexity AI</span>
                </div>
            </header>
            
            <div id="cards-container" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"></div>
            
            <footer class="mt-12 text-center text-gray-600 text-sm">
                <p>Powered by Perplexity AI & FinMind | 喵姆 AI 股市偵測站</p>
            </footer>
        </div>

        <button class="sidebar-toggle" onclick="toggleSidebar()">📋 追蹤清單</button>

        <div id="sidebar" class="sidebar">
            <h2 class="text-xl font-bold text-white mb-4">📋 追蹤清單管理</h2>
            <div class="mb-6">
                <input type="text" id="tickerInput" class="watchlist-input" placeholder="輸入股票代號 (如 2330)">
                <input type="text" id="nameInput" class="watchlist-input" placeholder="輸入股票名稱 (如 台積電)">
                <button id="addBtn" class="watchlist-btn" onclick="addStock()">➕ 新增追蹤</button>
            </div>
            <div class="text-sm text-gray-400 mb-2">目前追蹤 (<span id="stockCount">0</span> 檔)</div>
            <div id="watchlistContainer"></div>
            <button class="watchlist-btn" style="background: #6366f1; margin-top:20px" onclick="exportWatchlist()">📥 匯出清單</button>
            <button class="sidebar-toggle" style="right:auto; top:auto; position:relative; margin-top:20px; width:100%" onclick="toggleSidebar()">✖️ 關閉</button>
        </div>

        <script>
            // DATA & GLOBALS
            let stockData = {json_data};
            let watchlist = JSON.parse(localStorage.getItem('miaomo_watchlist')) || [];
            
            // SERVER MODE DETECTION
            const isServerMode = window.SERVER_MODE || false;

            // INITIALIZATION
            function init() {{
                if (watchlist.length === 0 && stockData.length > 0) {{
                    stockData.forEach(item => watchlist.push({{ ticker: item['代號'], name: item['名稱'] }}));
                    saveWatchlist();
                }}
                renderWatchlist();
                renderCards();
                
                // If in server mode, automatically fetch data for pending cards
                if (isServerMode) {{
                     checkPendingCards();
                }}
            }}

            // CORE RENDERING
            function renderCards() {{
                const container = document.getElementById('cards-container');
                container.innerHTML = '';
                
                const stockMap = new Map();
                stockData.forEach(item => stockMap.set(item['代號'], item));
                
                const renderList = watchlist.length > 0 ? watchlist : stockData.map(s => ({{ticker: s['代號'], name: s['名稱']}}));

                renderList.forEach((wItem, index) => {{
                    const item = stockMap.get(wItem.ticker);
                    const card = document.createElement('div');
                    
                    if (item) {{
                        renderStockCard(card, item, index);
                    }} else {{
                        renderPendingCard(card, wItem);
                    }}
                    container.appendChild(card);
                    
                    if (item) initRadarChart(item, index);
                }});
            }}

            function renderStockCard(card, item, index) {{
                const miaoScore = item.miao_score || item['評分'];
                const scoreClass = miaoScore >= 8 ? 'score-h' : (miaoScore <= 3 ? 'score-l' : 'score-m');
                const recClass = item['建議類別'] || 'action-hold';
                
                card.className = 'glass-card rounded-2xl overflow-hidden';
                card.innerHTML = `
                    <div class="p-6">
                        <div class="mb-4 text-center"><span class="action-badge ${{recClass}}">${{item['建議']}}</span></div>
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h2 class="text-xl font-bold text-white">${{item['名稱']}} <span class="text-sm text-gray-500">${{item['代號']}}</span></h2>
                                <div class="text-2xl font-mono mt-1 text-gray-200">$${{item['收盤價']}}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-sm text-gray-400">喵姆評分</div>
                                <div class="text-2xl font-bold ${{scoreClass}}">${{miaoScore}}</div>
                            </div>
                        </div>
                        
                        <div class="p-4 bg-gray-800/30 rounded-xl mb-4 text-sm text-gray-300">
                             ${{item['詳細理由']}}
                        </div>
                        
                        ${{item.ai_insight ? `
                        <div class="p-4 bg-blue-900/20 rounded-xl border border-blue-500/20 mb-4">
                            <p class="text-xs text-cyan-400 mb-1">🤖 AI 觀點</p>
                            <p class="text-sm text-gray-200">${{item.ai_insight}}</p>
                        </div>` : ''}}
                        
                        <div class="chart-container h-40"><canvas id="chart-${{item['代號']}}"></canvas></div>
                    </div>
                `;
            }}

            function renderPendingCard(card, wItem) {{
                card.id = `pending-${{wItem.ticker}}`;
                card.className = 'glass-card rounded-2xl overflow-hidden opacity-70 border-2 border-dashed border-gray-600';
                card.innerHTML = `
                    <div class="p-8 text-center h-full flex flex-col justify-center items-center">
                        <h2 class="text-xl font-bold text-gray-400 mb-2">${{wItem.name}} ${{wItem.ticker}}</h2>
                        <div class="text-4xl mb-4 loader-container">⏳</div>
                        <p class="text-gray-300 font-medium action-text">等待更新...</p>
                        ${{ !isServerMode ? '<p class="text-xs text-gray-500 mt-2">請重新執行程式</p>' : '' }}
                    </div>
                `;
            }}

            function initRadarChart(item, index) {{
                setTimeout(() => {{
                    const ctx = document.getElementById('chart-' + item['代號']);
                    if (ctx) {{
                        new Chart(ctx, {{
                            type: 'radar',
                            data: {{
                                labels: ['籌碼', '趨勢', 'MACD', 'RSI', '評分'],
                                datasets: [{{
                                    data: [
                                        item.chart_data.chips || 50, item.chart_data.tech_ma || 50,
                                        item.chart_data.tech_macd || 50, item.chart_data.tech_rsi || 50,
                                        item.chart_data.score || 50
                                    ],
                                    backgroundColor: 'rgba(56, 189, 248, 0.2)',
                                    borderColor: '#38bdf8',
                                    borderWidth: 2
                                }}]
                            }},
                            options: {{ scales: {{ r: {{ suggestedMin: 0, suggestedMax: 100, ticks: {{ display: false }} }} }}, plugins: {{ legend: {{ display: false }} }} }}
                        }});
                    }}
                }}, 0);
            }}

            // WATCHLIST & API ACTIONS
            async function addStock() {{
                const ticker = document.getElementById('tickerInput').value.trim().toUpperCase();
                const name = document.getElementById('nameInput').value.trim() || ticker;
                if (!ticker) return;
                
                if (watchlist.some(s => s.ticker === ticker)) {{ alert('已存在'); return; }}
                
                watchlist.push({{ ticker, name }});
                saveWatchlist();
                renderWatchlist();
                renderCards(); // This will render a pending card
                
                document.getElementById('tickerInput').value = '';
                document.getElementById('nameInput').value = '';
                
                if (isServerMode) {{
                    await fetchStockAnalysis(ticker, name);
                }}
            }}

            async function fetchStockAnalysis(ticker, name) {{
                const card = document.getElementById(`pending-${{ticker}}`);
                if (card) {{
                    card.querySelector('.loader-container').innerHTML = '<div class="loader"></div>';
                    card.querySelector('.action-text').textContent = 'AI 正在分析中...';
                }}
                
                try {{
                    const res = await fetch('/api/analyze', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ ticker, name }})
                    }});
                    
                    if (res.ok) {{
                        const data = await res.json();
                        // Add to stockData and re-render
                        stockData = stockData.filter(s => s['代號'] !== ticker); // remove old if any
                        stockData.push(data);
                        renderCards();
                        
                        // Also sync watchlist to server for persistence
                        fetch('/api/watchlist', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(watchlist)
                        }});
                    }} else {{
                        if(card) card.querySelector('.action-text').textContent = '分析失敗 (查無資料)';
                    }}
                }} catch (e) {{
                    console.error(e);
                    if(card) card.querySelector('.action-text').textContent = '連線錯誤';
                }}
            }}
            
            async function checkPendingCards() {{
                const pending = watchlist.filter(w => !stockData.find(s => s['代號'] === w.ticker));
                for (const w of pending) {{
                    await fetchStockAnalysis(w.ticker, w.name);
                }}
            }}

            function removeStock(index) {{
                if (confirm('確定移除?')) {{
                    watchlist.splice(index, 1);
                    saveWatchlist();
                    renderWatchlist();
                    renderCards();
                    if(isServerMode) {{
                        fetch('/api/watchlist', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(watchlist) }});
                    }}
                }}
            }}

            function saveWatchlist() {{ localStorage.setItem('miaomo_watchlist', JSON.stringify(watchlist)); }}
            
            function renderWatchlist() {{
                const container = document.getElementById('watchlistContainer');
                container.innerHTML = '';
                document.getElementById('stockCount').textContent = watchlist.length;
                watchlist.forEach((stock, index) => {{
                    const div = document.createElement('div');
                    div.className = 'flex justify-between items-center bg-gray-800/50 p-3 rounded mb-2';
                    div.innerHTML = `<span class="text-white">${{stock.ticker}} ${{stock.name}}</span><button onclick="removeStock(${{index}})" class="text-red-400">❌</button>`;
                    container.appendChild(div);
                }});
            }}
            
            function toggleSidebar() {{ document.getElementById('sidebar').classList.toggle('open'); }}
            
            function exportWatchlist() {{
                 const blob = new Blob([JSON.stringify({{stocks: watchlist}}, null, 2)], {{ type: 'application/json' }});
                 const a = document.createElement('a');
                 a.href = URL.createObjectURL(blob);
                 a.download = 'watchlist.json';
                 a.click();
            }}

            init();
        </script>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)


def send_line_push(msg):
    if not LINE_CHANNEL_TOKEN or not YOUR_USER_ID:
        print("⚠️ 未設定 LINE Token 或 User ID，跳過發送")
        return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}
    payload = {"to": YOUR_USER_ID, "messages": [{"type": "text", "text": msg}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("✅ LINE 通知已成功發送！")
        else:
            print(f"❌ LINE 發送失敗 (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")

def main():
    print("\n🐱 啟動喵姆 AI 股市偵測站 v10.0 (Perplexity 整合版)\n")
    
    # Debug Check
    if not PERPLEXITY_API_KEY:
        print(f"⚠️ 警告: 讀取到的 PERPLEXITY_API_KEY 為空！請檢查 .env 檔案。")
    else:
        masked_key = PERPLEXITY_API_KEY[:4] + "***" + PERPLEXITY_API_KEY[-4:] if len(PERPLEXITY_API_KEY) > 8 else "***"
        print(f"✅ 成功讀取 API Key (長度: {len(PERPLEXITY_API_KEY)}): {masked_key}")

    # 載入追蹤清單
    watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    if os.path.exists(watchlist_path):
        try:
            with open(watchlist_path, "r", encoding="utf-8") as f:
                watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
            print(f"📋 已載入追蹤清單：{len(my_portfolio)} 檔股票")
        except Exception as e:
            print(f"⚠️ 讀取 watchlist.json 失敗: {e}，使用預設清單")
            my_portfolio = [
                ("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
                ("0056", "元大高股息"), ("00919", "群益高股息")
            ]
    else:
        print("⚠️ 找不到 watchlist.json，使用預設清單")
        my_portfolio = [
            ("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
            ("0056", "元大高股息"), ("00919", "群益高股息")
        ]
    
    excel_data = []
    line_msg = f"🐱 【喵姆 AI 股市偵測站】\n📅 {datetime.now().strftime('%Y-%m-%d')}\n基於多維度指標與 AI 調研的自動化決策系統\n"
    
    # AI Buffer Header
    # AI Buffer Header
    buffer_content = "你現在是頂尖分析師，請針對以下資料進行跨維度的批判性分析，找出潛在漏洞。\n\n"
    
    # 初始化 DataLoader (避免重複登入)
    dl = DataLoader()
    
    # 簡單驗證 Token 格式，避免使用無效/截斷的 Token 導致 API 錯誤
    if FINMIND_TOKEN and len(FINMIND_TOKEN) > 50 and not FINMIND_TOKEN.endswith("..."):
        print(f"🔑 正在登入 FinMind (Token長度: {len(FINMIND_TOKEN)})...")
        try:
            dl.login_by_token(api_token=FINMIND_TOKEN)
        except Exception as e:
            print(f"⚠️ 登入失敗，將使用訪客權限: {e}")
    else:
        print("⚠️ 檢測到 FinMind Token 無效或是使用預設截斷值（Guest Mode）")
        print("   -> 將使用訪客權限抓取資料 (可能有筆數限制)")
        
    for stock_id, stock_name in my_portfolio:
        # 使用新模組分析
        res = analyze_stock(dl, stock_id, stock_name, PERPLEXITY_API_KEY)
        if res:
            excel_data.append(res)
            
            # Line Message & Buffer Logic (v12 結構適配)
            snapshot = res.get('snapshot', {})
            meta = res.get('meta', {})
            score = snapshot.get('score', snapshot.get('評分', 5))
            
            if score >= 8 or score <= 3:
                icon = "🔥" if score >= 8 else "💀"
                
                line_msg += f"\n{'='*18}\n"
                line_msg += f"{icon} {meta.get('name', stock_name)}({meta.get('ticker', stock_id)}) ${meta.get('close', 'N/A')}\n"
                line_msg += f"🐱 喵姆評分: {score}\n"
                line_msg += f"📊 建議: {snapshot.get('action', snapshot.get('建議', 'N/A'))}\n"
                line_msg += f"💬 {snapshot.get('human_summary', '')}\n"
                
                ai_insight = res.get('logic', {}).get('ai_analysis', res.get('ai_insight', ''))
                if ai_insight:
                    line_msg += f"🤖 AI觀點: {ai_insight[:100]}...\n"
                
                # 更新 Buffer
                buffer_content += f"【{stock_name}】喵姆評分:{score}\n{snapshot.get('human_summary','')}\n{'-'*50}\n"
                line_msg += f"🔍 點此查看：https://www.perplexity.ai/search?q=分析{stock_name}{stock_id}今日動態\n"
                
        time.sleep(1) # 避免 API 速率限制
        
    index_html_path = os.path.abspath("index.html")
    line_msg += f"\n🐱 喵姆偵測站已更新：\nfile://{index_html_path}"
    
    # Auto Open
    print(f"🚀 自動開啟戰情室: {index_html_path}")
    os.system(f"open '{index_html_path}'")
    
    print(line_msg)
    
    # 寫入 Buffer 檔案
    try:
        with open("Transfer_to_AI.txt", "w", encoding="utf-8") as f:
            f.write(buffer_content)
        print("✅ Transfer_to_AI.txt 已生成")
    except Exception as e:
        print(f"❌ Buffer 檔案寫入失敗: {e}")

    send_line_push(line_msg)
    
    try:
        # Convert 3-layer packet to flat dict for Excel
        flat_data = []
        for d in excel_data:
            # 相容性檢查：如果資料結構是新的 v12.0
            if 'snapshot' in d:
                snapshot = d.get('snapshot', {})
                flat = {
                    "代號": d['meta']['ticker'],
                    "名稱": d['meta']['name'],
                    "收盤": d['meta']['close'],
                    "建議": snapshot.get('action', snapshot.get('建議', 'N/A')),
                    "評分": snapshot.get('score', snapshot.get('評分', 5)),
                    "外資": d.get('evidence', {}).get('foreign', {}).get('desc', ''),
                    "RSI": d.get('evidence', {}).get('technical', {}).get('rsi', 50),
                    "摘要": snapshot.get('human_summary', snapshot.get('詳細理由', '')),
                    "AI觀點": d.get('logic', {}).get('ai_analysis', '')
                }
                flat_data.append(flat)
            else:
                # 舊格式 fallback
                flat_data.append(d)

        df = pd.DataFrame(flat_data)
        if 'reasons_raw' in df.columns: del df['reasons_raw']
        
        filename = f"股市日報_{datetime.now().strftime('%Y%m%d')}.xlsx"
        df.to_excel(filename, index=False)
        print(f"\n✅ 成功建立 Excel 報表：{filename}")
        
        # Pass ORIGINAL full-structure data to HTML generator
        generate_index_html(excel_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 報表儲存失敗: {e}")

def generate_index_html(data):
    """
    生成喵姆 AI 股市偵測站的互動式報表 (index.html)
    包含 Chart.js 五軸雷達圖與 Tab 切換（雷達分析 / AI 觀點）
    
    支援資料格式:
    - v12.0 格式: { meta, snapshot, evidence, logic }
    - 舊格式: { 評分, 建議, chart_data, ... }
    """
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 資料適配層：將 v12.0 格式轉換為 UI 需要的格式
    adapted_data = []
    for item in data:
        if 'meta' in item:  # v12.0 格式
            snapshot = item.get('snapshot', {})
            evidence = item.get('evidence', {})
            logic = item.get('logic', {})
            tech = evidence.get('technical', {})
            
            # 從 v12 資料重建雷達圖數據
            rsi = tech.get('rsi', 50)
            macd_cross = 80 if tech.get('macd_cross') == 'golden' else 20
            ma_above = 80 if tech.get('ma_position', '') == 'above' else 20
            foreign_net = evidence.get('foreign', {}).get('net', 0)
            chips = min(100, max(0, 50 + int(foreign_net/200)))  # 正規化
            
            score = snapshot.get('score', snapshot.get('評分', 5))
            
            adapted = {
                '代號': item['meta']['ticker'],
                '名稱': item['meta']['name'],
                '收盤價': item['meta']['close'],
                '評分': score,
                'miao_score': score,  # v12 不區分這兩個
                '建議': snapshot.get('action', '觀望'),
                '建議類別': snapshot.get('action_class', 'action-hold'),
                '外資動向': evidence.get('foreign', {}).get('desc', 'N/A'),
                '詳細理由': snapshot.get('human_summary', ''),
                'ai_insight': logic.get('ai_analysis', '📊 評分未達觸發門檻，暫無深度分析'),
                'chart_data': {
                    'chips': chips,
                    'tech_ma': ma_above,
                    'tech_macd': macd_cross,
                    'tech_rsi': rsi,
                    'score': score * 10
                }
            }
            adapted_data.append(adapted)
        else:
            # 舊格式，直接使用
            adapted_data.append(item)
    
    json_data = json.dumps(adapted_data, ensure_ascii=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>喵姆 AI 股市偵測站 {date_str}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Space+Grotesk:wght@300;400;500;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-primary: #0a0e1a;
                --bg-card: rgba(20, 30, 50, 0.85);
                --accent-cyan: #38bdf8;
                --accent-purple: #a855f7;
                --accent-green: #4ade80;
                --accent-red: #f87171;
            }}
            body {{ 
                background: linear-gradient(135deg, var(--bg-primary) 0%, #1a1a2e 50%, #16213e 100%);
                color: #e2e8f0; 
                font-family: 'Noto Sans TC', 'Space Grotesk', sans-serif;
                min-height: 100vh;
            }}
            .glass-card {{ 
                background: var(--bg-card);
                backdrop-filter: blur(20px); 
                border: 1px solid rgba(255, 255, 255, 0.08);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
                transition: all 0.3s ease;
            }}
            .glass-card:hover {{
                transform: translateY(-4px);
                box-shadow: 0 12px 48px rgba(56, 189, 248, 0.15);
                border-color: rgba(56, 189, 248, 0.3);
            }}
            .tab-btn {{ 
                position: relative;
                transition: all 0.2s ease;
            }}
            .tab-btn::after {{
                content: '';
                position: absolute;
                bottom: 0;
                left: 50%;
                width: 0;
                height: 2px;
                background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
                transition: all 0.3s ease;
                transform: translateX(-50%);
            }}
            .tab-btn.active::after {{ width: 100%; }}
            .tab-btn.active {{ color: var(--accent-cyan); }}
            .score-h {{ color: var(--accent-green); text-shadow: 0 0 20px rgba(74, 222, 128, 0.5); }}
            .score-m {{ color: var(--accent-cyan); text-shadow: 0 0 20px rgba(56, 189, 248, 0.5); }}
            .score-l {{ color: var(--accent-red); text-shadow: 0 0 20px rgba(248, 113, 113, 0.5); }}
            .chart-container {{
                position: relative;
            }}
            .kirin-center {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                pointer-events: none;
                z-index: 10;
            }}
            .kirin-value {{
                font-size: 2rem;
                font-weight: 700;
                line-height: 1;
            }}
            .kirin-label {{
                font-size: 0.6rem;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-top: 2px;
            }}
            /* 行動建議大標籤 */
            .action-badge {{
                display: inline-block;
                padding: 0.75rem 1.5rem;
                border-radius: 12px;
                font-size: 1.1rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                animation: badge-pulse 2s infinite;
            }}
            .action-buy {{
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                border: 2px solid #34d399;
                box-shadow: 0 4px 20px rgba(16, 185, 129, 0.4);
            }}
            .action-bullish {{
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                color: white;
                border: 2px solid #fbbf24;
                box-shadow: 0 4px 20px rgba(245, 158, 11, 0.4);
            }}
            .action-hold {{
                background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
                color: white;
                border: 2px solid #9ca3af;
                box-shadow: 0 4px 15px rgba(107, 114, 128, 0.3);
            }}
            .action-sell {{
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                color: white;
                border: 2px solid #f87171;
                box-shadow: 0 4px 20px rgba(239, 68, 68, 0.4);
                animation: danger-pulse 1s infinite;
            }}
            .action-caution {{
                background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%);
                color: white;
                border: 2px solid #fb923c;
                box-shadow: 0 4px 20px rgba(234, 88, 12, 0.4);
            }}
            @keyframes badge-pulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
            }}
            @keyframes danger-pulse {{
                0%, 100% {{ opacity: 1; box-shadow: 0 4px 20px rgba(239, 68, 68, 0.4); }}
                50% {{ opacity: 0.9; box-shadow: 0 4px 30px rgba(239, 68, 68, 0.6); }}
            }}
            .pulse-ring {{
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.5; }}
                100% {{ opacity: 1; }}
            }}
            .gradient-text {{
                background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-purple) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            /* Sidebar for Watchlist */
            .sidebar {{ 
                position: fixed; right: 0; top: 0; width: 320px; height: 100%; 
                background: #1e293b; transform: translateX(100%); transition: 0.3s; 
                z-index: 50; border-left: 1px solid #334155; padding: 20px; 
            }}
            .sidebar.open {{ transform: translateX(0); }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <header class="mb-12 flex flex-col md:flex-row justify-between items-center">
                <div class="text-center md:text-left">
                    <h1 class="text-4xl font-bold gradient-text mb-2">
                        🐱 喵姆 AI 股市偵測站
                    </h1>
                    <p class="text-gray-400">基於多維度指標與 AI 調研的自動化決策系統 • {date_str}</p>
                </div>
                <div class="mt-4 md:mt-0 flex gap-3">
                   <span class="px-4 py-2 rounded-full bg-cyan-900/30 text-cyan-400 text-sm border border-cyan-800/50 backdrop-blur">
                     🎯 喵姆評分系統
                   </span>
                   <span class="px-4 py-2 rounded-full bg-purple-900/30 text-purple-400 text-sm border border-purple-800/50 backdrop-blur pulse-ring">
                     🤖 Perplexity AI 加持
                   </span>
                   <button onclick="toggleSidebar()" class="px-4 py-2 rounded-full bg-slate-700 text-slate-300 text-sm border border-slate-600 hover:bg-slate-600 transition">
                     📋 追蹤清單
                   </button>
                </div>
            </header>
            
            <div id="cards-container" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            </div>
            
            <footer class="mt-12 text-center text-gray-600 text-sm">
                <p>Powered by Perplexity AI & FinMind | 本報告僅供參考，投資風險請自負 | 喵姆 AI 股市偵測站</p>
            </footer>
        </div>
        
        <!-- Sidebar for Watchlist Management -->
        <div id="sidebar" class="sidebar">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-bold text-white">📋 追蹤清單</h3>
                <button onclick="toggleSidebar()" class="text-gray-400 hover:text-white text-2xl">&times;</button>
            </div>
            <div id="watchlist-items" class="space-y-2 max-h-[70vh] overflow-y-auto"></div>
            <div class="mt-4 pt-4 border-t border-slate-600">
                <input id="new-stock-input" type="text" placeholder="輸入股票代號 (如 2330)" 
                       class="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white text-sm mb-2">
                <button onclick="addToWatchlist()" class="w-full py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white text-sm font-medium transition">
                    ＋ 加入追蹤
                </button>
            </div>
        </div>

        <script>
            const stockData = {json_data};
            let watchlist = JSON.parse(localStorage.getItem('miaomo_watchlist')) || [];
            
            function getScoreClass(score) {{
                if (score >= 8) return 'score-h';
                if (score <= 3) return 'score-l';
                return 'score-m';
            }}
            
            function getScoreColor(score) {{
                if (score >= 8) return '#4ade80';
                if (score <= 3) return '#f87171';
                return '#38bdf8';
            }}
            
            function renderCards() {{
                const container = document.getElementById('cards-container');
                container.innerHTML = '';
                
                stockData.forEach((item, index) => {{
                    const baseScore = item['評分'];
                    const miaoScore = item['miao_score'] || baseScore;
                    const scoreClass = getScoreClass(miaoScore);
                    const scoreColor = getScoreColor(miaoScore);
                    const aiContent = item.ai_insight || '📊 評分未達觸發門檻，暫無深度分析';
                    
                    const card = document.createElement('div');
                    card.className = 'glass-card rounded-2xl overflow-hidden';
                    const recClass = item['建議類別'] || 'action-hold';
                    card.innerHTML = `
                        <div class="p-6">
                            <!-- 行動建議大標籤 - 放在最上方 -->
                            <div class="mb-4 text-center">
                                <span class="action-badge ${{recClass}}">${{item['建議']}}</span>
                            </div>
                            
                            <div class="flex justify-between items-start mb-4">
                                <div>
                                    <h2 class="text-xl font-bold text-white">${{item['名稱']}} <span class="text-sm text-gray-500 font-normal">${{item['代號']}}</span></h2>
                                    <div class="text-2xl font-mono mt-1 text-gray-200">$${{typeof item['收盤價'] === 'number' ? item['收盤價'].toFixed(2) : item['收盤價']}}</div>
                                </div>
                                <div class="text-right">
                                    <div class="text-sm text-gray-400">喵姆評分</div>
                                    <div class="text-2xl font-bold ${{scoreClass}}">${{miaoScore}}</div>
                                </div>
                            </div>

                            <div class="flex border-b border-gray-700/50 mb-4">
                                <button onclick="switchTab(${{index}}, 'data')" id="tab-data-${{index}}" class="tab-btn active px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200">📊 雷達分析</button>
                                <button onclick="switchTab(${{index}}, 'ai')" id="tab-ai-${{index}}" class="tab-btn px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200">🤖 AI 觀點</button>
                            </div>

                            <div id="view-data-${{index}}" class="view-content block">
                                <div class="chart-container h-52 mb-4">
                                    <canvas id="chart-${{index}}"></canvas>
                                    <div class="kirin-center">
                                        <div class="kirin-value ${{scoreClass}}">${{miaoScore}}</div>
                                        <div class="kirin-label">喵姆評分</div>
                                    </div>
                                </div>
                                <div class="space-y-2 text-sm">
                                    <div class="flex justify-between p-3 bg-gray-800/30 rounded-lg border border-gray-700/30">
                                        <span class="text-gray-400">📈 外資動向</span>
                                        <span class="${{item['外資動向'] && item['外資動向'].includes('-') ? 'text-red-400' : 'text-green-400'}} font-mono font-medium">${{item['外資動向'] || 'N/A'}}</span>
                                    </div>
                                    <div class="p-3 bg-gray-800/30 rounded-lg border border-gray-700/30 text-xs text-gray-300 leading-relaxed">
                                        ${{item['詳細理由'] || '無詳細資料'}}
                                    </div>
                                </div>
                            </div>
                            
                            <div id="view-ai-${{index}}" class="view-content hidden">
                                <div class="p-4 bg-gradient-to-br from-blue-900/20 to-purple-900/20 rounded-xl border border-blue-500/20 mb-4">
                                    <p class="text-xs font-semibold text-cyan-400 mb-2 uppercase tracking-wider">🤖 Perplexity AI 深度分析</p>
                                    <p class="text-gray-200 leading-relaxed text-sm">${{aiContent}}</p>
                                </div>
                                <a href="https://www.perplexity.ai/search?q=分析${{item['名稱']}}${{item['代號']}}今日動態" target="_blank" 
                                   class="block w-full text-center py-3 rounded-xl bg-gradient-to-r from-cyan-600/80 to-purple-600/80 hover:from-cyan-500 hover:to-purple-500 transition-all text-sm font-medium text-white shadow-lg">
                                    🔍 前往 Perplexity 深度追蹤
                                </a>
                            </div>
                        </div>
                    `;
                    container.appendChild(card);
                    
                    // Render Radar Chart with center Kirin Index (5-axis spider web)
                    const ctx = document.getElementById('chart-' + index);
                    if (ctx && item.chart_data) {{
                        new Chart(ctx, {{
                            type: 'radar',
                            data: {{
                                labels: ['籌碼面', '季線趨勢', 'MACD', 'RSI', '綜合分'],
                                datasets: [{{
                                    label: '技術指標',
                                    data: [
                                        item.chart_data.chips || 50,
                                        item.chart_data.tech_ma || 50,
                                        item.chart_data.tech_macd || 50,
                                        item.chart_data.tech_rsi || 50,
                                        item.chart_data.score || 50
                                    ],
                                    backgroundColor: scoreColor + '22',
                                    borderColor: scoreColor,
                                    borderWidth: 2,
                                    pointBackgroundColor: scoreColor,
                                    pointBorderColor: '#fff',
                                    pointBorderWidth: 1,
                                    pointRadius: 4
                                }}]
                            }},
                            options: {{
                                responsive: true,
                                maintainAspectRatio: false,
                                scales: {{
                                    r: {{
                                        angleLines: {{ color: 'rgba(255, 255, 255, 0.08)' }},
                                        grid: {{ color: 'rgba(255, 255, 255, 0.08)', circular: true }},
                                        pointLabels: {{ 
                                            color: '#94a3b8', 
                                            font: {{ size: 10, family: 'Noto Sans TC' }},
                                            padding: 15
                                        }},
                                        suggestedMin: 0,
                                        suggestedMax: 100,
                                        ticks: {{ display: false }}
                                    }}
                                }},
                                plugins: {{ 
                                    legend: {{ display: false }}
                                }}
                            }}
                        }});
                    }}
                }});
                
                // Auto populate watchlist from data if empty
                if (watchlist.length === 0 && stockData.length > 0) {{
                    stockData.forEach(d => {{
                        watchlist.push({{ticker: d['代號'], name: d['名稱']}});
                    }});
                    saveWatchlist();
                }}
            }}

            function switchTab(index, tab) {{
                document.getElementById('view-data-' + index).classList.add('hidden');
                document.getElementById('view-ai-' + index).classList.add('hidden');
                document.getElementById('tab-data-' + index).classList.remove('active');
                document.getElementById('tab-ai-' + index).classList.remove('active');
                
                document.getElementById('view-' + tab + '-' + index).classList.remove('hidden');
                document.getElementById('tab-' + tab + '-' + index).classList.add('active');
            }}
            
            function toggleSidebar() {{
                document.getElementById('sidebar').classList.toggle('open');
                renderWatchlist();
            }}
            
            function renderWatchlist() {{
                const container = document.getElementById('watchlist-items');
                container.innerHTML = watchlist.map((item, i) => `
                    <div class="flex justify-between items-center p-2 bg-slate-800 rounded-lg">
                        <span class="text-white text-sm">${{item.ticker}} ${{item.name || ''}}</span>
                        <button onclick="removeFromWatchlist(${{i}})" class="text-red-400 hover:text-red-300 text-sm">✕</button>
                    </div>
                `).join('');
            }}
            
            function addToWatchlist() {{
                const input = document.getElementById('new-stock-input');
                const ticker = input.value.trim();
                if (ticker && !watchlist.some(w => w.ticker === ticker)) {{
                    watchlist.push({{ ticker, name: '' }});
                    saveWatchlist();
                    renderWatchlist();
                    input.value = '';
                }}
            }}
            
            function removeFromWatchlist(index) {{
                watchlist.splice(index, 1);
                saveWatchlist();
                renderWatchlist();
            }}
            
            function saveWatchlist() {{
                localStorage.setItem('miaomo_watchlist', JSON.stringify(watchlist));
            }}
            
            renderCards();
        </script>
    </body>
    </html>
    """
    
    try:
        output_path = os.path.abspath("index.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"\n✅ 一頁式戰情室已生成：{output_path}")
    except Exception as e:
        print(f"❌ HTML 報表建立失敗: {e}")

if __name__ == "__main__":
    main()
