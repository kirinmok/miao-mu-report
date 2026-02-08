import os
import json
import secrets
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import google.generativeai as genai
from PIL import Image
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# ==========================================
# 📊 基金經理人後台 (Fund Manager Backend)
# ==========================================

load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 載入 Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

ADMIN_USER = "admin"
ADMIN_PASS = "admin888"

ASSETS_FILE = "family_assets.json"

def load_assets():
    if not os.path.exists(ASSETS_FILE):
        default_data = {"莫老師": {"cash": 0, "holdings": []}}
        with open(ASSETS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return default_data
    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_assets(data):
    with open(ASSETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    is_logged_in = 'admin_logged_in' in session
    assets = load_assets() if is_logged_in else {}
    current_profile = session.get('current_profile', list(assets.keys())[0] if assets else None)
    
    user_data = assets.get(current_profile, {"cash": 0, "holdings": []}) if is_logged_in else None
    
    return render_template('index.html', 
                           is_logged_in=is_logged_in, 
                           assets=assets, 
                           current_profile=current_profile, 
                           user_data=user_data)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    if username == ADMIN_USER and password == ADMIN_PASS:
        session['admin_logged_in'] = True
        return redirect(url_for('index'))
    flash('管理員認證失敗', 'error')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/switch_profile', methods=['POST'])
def switch_profile():
    if 'admin_logged_in' not in session:
        return redirect(url_for('index'))
    profile_name = request.form.get('profile_name')
    session['current_profile'] = profile_name
    return redirect(url_for('index'))

@app.route('/update_assets', methods=['POST'])
def update_assets():
    if 'admin_logged_in' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    profile = session.get('current_profile')
    try:
        new_data = request.json
        assets = load_assets()
        assets[profile] = new_data
        save_assets(assets)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/upload_screenshot', methods=['POST'])
def upload_screenshot():
    if 'admin_logged_in' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    if file.filename == '' or not GEMINI_API_KEY:
        return jsonify({"error": "Invalid upload or API key"}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(filepath)
        
        prompt = """
        請分析這張股票庫存截圖。回傳 JSON list，包含:
        - symbol (代號, 字串)
        - name (名稱, 字串)
        - shares (股數, 整數)
        - cost (平均成本, 浮點數)
        若無資料或非庫存圖，請僅回傳空列表 []。不要輸出 Markdown 格式。
        """
        
        response = model.generate_content([prompt, img])
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[-1].split("```")[0].strip()
        
        recognized_holdings = json.loads(raw_text)
        return jsonify({"success": True, "holdings": recognized_holdings})
    except Exception as e:
        return jsonify({"error": f"AI 辨識失敗: {str(e)}"}), 500
    finally:
        if os.path.exists(filepath): os.remove(filepath)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
