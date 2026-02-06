#!/usr/bin/env python3
"""
喵姆 AI 股市偵測站 - 後台伺服器
支援密碼保護的管理界面，可即時編輯追蹤清單並觸發分析
"""
import os
import json
import hashlib
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# 管理員密碼 (可在 .env 設定 ADMIN_PASSWORD)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "miaomurocks")

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", "miaomupurr2026")

WATCHLIST_FILE = "watchlist.json"

# ============================================================
# 工具函數
# ============================================================

def load_watchlist_data():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 確保格式正確
                if isinstance(data, list):
                    return {"stocks": data}
                return data
        except:
            return {"stocks": []}
    return {"stocks": []}

def save_watchlist_data(data):
    if "stocks" not in data:
        data = {"stocks": data if isinstance(data, list) else []}
    data["updated_at"] = datetime.now().isoformat()
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def require_admin(f):
    """裝飾器：需要管理員權限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "需要管理員權限", "need_login": True}), 401
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# 公開路由
# ============================================================

@app.route("/")
def index():
    """公開首頁 - 顯示報表"""
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 注入 Server Mode 標記
        is_admin = session.get("is_admin", False)
        injection = f"""
        <script>
            window.SERVER_MODE = true;
            window.IS_ADMIN = {str(is_admin).lower()};
            console.log("🚀 Server Mode | Admin: {str(is_admin).lower()}");
        </script>
        </head>
        """
        content = content.replace("</head>", injection)
        return content
    return "請先執行 python3 main.py 生成 index.html"

@app.route("/api/status")
def api_status():
    """檢查伺服器狀態和登入狀態"""
    return jsonify({
        "server": "running",
        "is_admin": session.get("is_admin", False),
        "watchlist_count": len(load_watchlist_data().get("stocks", []))
    })

# ============================================================
# 管理員登入
# ============================================================

@app.route("/admin")
def admin_page():
    """管理後台頁面"""
    if not session.get("is_admin"):
        return redirect(url_for("login_page"))
    
    # 簡單的管理界面
    watchlist = load_watchlist_data()
    stocks_html = ""
    for s in watchlist.get("stocks", []):
        ticker = s.get("ticker", s) if isinstance(s, dict) else s
        name = s.get("name", "") if isinstance(s, dict) else ""
        stocks_html += f'<div class="stock-item"><span>{ticker} {name}</span><button onclick="removeStock(\'{ticker}\')">❌</button></div>'
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🔐 喵姆管理後台</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: system-ui, sans-serif; background: #0f172a; color: white; padding: 20px; }}
            h1 {{ color: #fbbf24; margin-bottom: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
            input {{ width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; margin-bottom: 10px; }}
            button {{ padding: 12px 20px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; }}
            .btn-primary {{ background: #10b981; color: white; width: 100%; }}
            .btn-danger {{ background: #ef4444; color: white; }}
            .btn-warning {{ background: #f59e0b; color: black; width: 100%; margin-top: 10px; }}
            .stock-item {{ display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #334155; border-radius: 8px; margin-bottom: 8px; }}
            .stock-item button {{ padding: 5px 10px; }}
            .status {{ padding: 10px; border-radius: 8px; margin-bottom: 15px; }}
            .status.success {{ background: #064e3b; }}
            .status.error {{ background: #7f1d1d; }}
            #status {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 喵姆管理後台</h1>
            
            <div id="status" class="status"></div>
            
            <div class="card">
                <h3 style="margin-bottom:15px">➕ 新增股票</h3>
                <input type="text" id="ticker" placeholder="股票代號 (例: 00881)">
                <input type="text" id="name" placeholder="股票名稱 (例: 國泰台灣5G+)">
                <button class="btn-primary" onclick="addStock()">新增追蹤</button>
            </div>
            
            <div class="card">
                <h3 style="margin-bottom:15px">📋 目前追蹤清單 ({len(watchlist.get("stocks", []))} 檔)</h3>
                <div id="stockList">{stocks_html if stocks_html else '<p style="color:#94a3b8">尚無追蹤股票</p>'}</div>
            </div>
            
            <div class="card">
                <button class="btn-warning" onclick="runAnalysis()">🚀 執行分析並更新網頁</button>
                <p style="color:#94a3b8;font-size:12px;margin-top:10px">點擊後會重新分析所有股票並更新 index.html</p>
            </div>
            
            <div class="card" style="background:#7f1d1d">
                <button class="btn-danger" onclick="logout()" style="width:100%">🚪 登出</button>
            </div>
        </div>
        
        <script>
            function showStatus(msg, isError) {{
                const el = document.getElementById('status');
                el.textContent = msg;
                el.className = 'status ' + (isError ? 'error' : 'success');
                el.style.display = 'block';
                setTimeout(() => el.style.display = 'none', 3000);
            }}
            
            async function addStock() {{
                const ticker = document.getElementById('ticker').value.trim();
                const name = document.getElementById('name').value.trim();
                if (!ticker) {{ showStatus('請輸入股票代號', true); return; }}
                
                const res = await fetch('/api/admin/watchlist/add', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ ticker, name }})
                }});
                const data = await res.json();
                if (res.ok) {{
                    showStatus('✅ 已新增 ' + ticker);
                    location.reload();
                }} else {{
                    showStatus(data.error, true);
                }}
            }}
            
            async function removeStock(ticker) {{
                if (!confirm('確定移除 ' + ticker + '?')) return;
                const res = await fetch('/api/admin/watchlist/remove', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ ticker }})
                }});
                if (res.ok) {{
                    showStatus('✅ 已移除 ' + ticker);
                    location.reload();
                }}
            }}
            
            async function runAnalysis() {{
                showStatus('⏳ 正在執行分析，請稍候...', false);
                const res = await fetch('/api/admin/run-analysis', {{ method: 'POST' }});
                const data = await res.json();
                if (res.ok) {{
                    showStatus('✅ 分析完成！網頁已更新');
                    setTimeout(() => window.open('/', '_blank'), 1000);
                }} else {{
                    showStatus(data.error, true);
                }}
            }}
            
            function logout() {{
                fetch('/api/admin/logout', {{ method: 'POST' }}).then(() => location.href = '/');
            }}
        </script>
    </body>
    </html>
    """

@app.route("/login")
def login_page():
    """登入頁面"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🔐 管理員登入</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: system-ui, sans-serif; background: #0f172a; color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .card { background: #1e293b; border-radius: 16px; padding: 40px; width: 100%; max-width: 400px; }
            h1 { color: #fbbf24; margin-bottom: 30px; text-align: center; }
            input { width: 100%; padding: 15px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; margin-bottom: 20px; font-size: 16px; }
            button { width: 100%; padding: 15px; border-radius: 8px; border: none; background: #10b981; color: white; font-size: 16px; font-weight: bold; cursor: pointer; }
            button:hover { background: #059669; }
            .error { color: #ef4444; text-align: center; margin-bottom: 15px; display: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🐱 喵姆管理後台</h1>
            <div id="error" class="error">密碼錯誤</div>
            <form onsubmit="login(event)">
                <input type="password" id="password" placeholder="請輸入管理員密碼" autofocus>
                <button type="submit">登入</button>
            </form>
        </div>
        <script>
            async function login(e) {
                e.preventDefault();
                const password = document.getElementById('password').value;
                const res = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ password })
                });
                if (res.ok) {
                    location.href = '/admin';
                } else {
                    document.getElementById('error').style.display = 'block';
                }
            }
        </script>
    </body>
    </html>
    """

@app.route("/api/admin/login", methods=["POST"])
def api_login():
    """管理員登入 API"""
    data = request.json or {}
    password = data.get("password", "")
    
    if password == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "密碼錯誤"}), 401

@app.route("/api/admin/logout", methods=["POST"])
def api_logout():
    """管理員登出"""
    session.pop("is_admin", None)
    return jsonify({"status": "ok"})

# ============================================================
# 管理員專用 API
# ============================================================

@app.route("/api/admin/watchlist/add", methods=["POST"])
@require_admin
def api_add_stock():
    """新增股票到追蹤清單"""
    data = request.json or {}
    ticker = data.get("ticker", "").strip()
    name = data.get("name", "").strip()
    
    if not ticker:
        return jsonify({"error": "請輸入股票代號"}), 400
    
    watchlist = load_watchlist_data()
    stocks = watchlist.get("stocks", [])
    
    # 檢查是否已存在
    for s in stocks:
        existing_ticker = s.get("ticker", s) if isinstance(s, dict) else s
        if existing_ticker == ticker:
            return jsonify({"error": f"{ticker} 已在追蹤清單中"}), 400
    
    stocks.append({"ticker": ticker, "name": name})
    watchlist["stocks"] = stocks
    save_watchlist_data(watchlist)
    
    return jsonify({"status": "ok", "message": f"已新增 {ticker}"})

@app.route("/api/admin/watchlist/remove", methods=["POST"])
@require_admin
def api_remove_stock():
    """從追蹤清單移除股票"""
    data = request.json or {}
    ticker = data.get("ticker", "").strip()
    
    watchlist = load_watchlist_data()
    stocks = watchlist.get("stocks", [])
    
    new_stocks = []
    for s in stocks:
        existing_ticker = s.get("ticker", s) if isinstance(s, dict) else s
        if existing_ticker != ticker:
            new_stocks.append(s)
    
    watchlist["stocks"] = new_stocks
    save_watchlist_data(watchlist)
    
    return jsonify({"status": "ok"})

@app.route("/api/admin/run-analysis", methods=["POST"])
@require_admin
def api_run_analysis():
    """執行完整分析並更新 index.html"""
    import subprocess
    
    try:
        print("🚀 管理員觸發分析...")
        result = subprocess.run(
            ["python3", "main.py"],
            capture_output=True,
            text=True,
            timeout=300  # 5分鐘超時
        )
        
        if result.returncode == 0:
            return jsonify({"status": "ok", "message": "分析完成"})
        else:
            return jsonify({"error": f"分析失敗: {result.stderr[:200]}"}), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({"error": "分析超時 (5分鐘)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 啟動
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🐱 喵姆 AI 戰情室 - 後台伺服器")
    print("="*50)
    print(f"\n📊 公開報表: http://localhost:5000")
    print(f"🔐 管理後台: http://localhost:5000/admin")
    print(f"🔑 預設密碼: {ADMIN_PASSWORD}")
    print(f"\n💡 可在 .env 設定 ADMIN_PASSWORD 更改密碼\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
