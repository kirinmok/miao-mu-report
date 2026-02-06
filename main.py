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
# 喵姆 AI 股市偵測站 v10.0 (Perplexity 整合版)
# ==========================================

# 1. 載入設定
load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN")
YOUR_USER_ID = os.getenv("USER_ID") # 注意：.env 裡是用 USER_ID，但程式碼裡變數可能有異，這裡統一用 config
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

class ProAnalyzer:
    @staticmethod
    def calculate_indicators(df):
        """
        [內建數學核心] 直接用 Pandas 計算，不需外部套件
        """
        df = df.sort_values('date')
        close = df['close']

        # A. 計算季線 (60MA)
        df['SMA_60'] = close.rolling(window=60).mean()

        # B. 計算 MACD
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # C. 計算 RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        return df

    @staticmethod
    def ask_perplexity(stock_name, stock_id, score, reasons):
        """
        呼叫 Perplexity API 進行深度研究
        """
        if not PERPLEXITY_API_KEY:
            return "⚠️ 未設定 Perplexity API Key，無法進行 AI 分析。"

        print(f"🤖 AI 正在研究: {stock_name}...")
        
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = "你是一位精通台股的資深分析師。請根據使用者提供的股票與數據，搜尋最新新聞與財報，給出簡短精闢的漲跌原因分析（限 50 字以內）。請務必在回答開頭標註【正面】、【負面】或【中立】。"
        user_content = f"股票：{stock_name} ({stock_id})\n目前評分：{score}\n技術面訊號：{reasons}\n請分析為何出現此評分？最近有什麼利多或利空新聞？"

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
        print(f"🚀 分析中: {stock_name} ({stock_id})...")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
            
            # dl (DataLoader) is passed from outside
            df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df.empty: return None

            df = ProAnalyzer.calculate_indicators(df)

            # 籌碼分析
            df_chips = dl.taiwan_stock_institutional_investors(
                stock_id=stock_id, start_date=start_date, end_date=end_date
            )
            
            foreign_msg = "外資中立"
            foreign_display = "調節持股 (小幅買超)"  # 新增：用於 HTML 顯示的更詳細描述
            foreign_score = 0
            net_buy = 0
            
            if not df_chips.empty:
                df_foreign = df_chips[df_chips['name'] == 'Foreign_Investor']
                if not df_foreign.empty:
                    last_5_days = df_foreign.tail(5)  # 改用近5日
                    net_buy = (last_5_days['buy'].sum() - last_5_days['sell'].sum()) // 1000
                    
                    # 新版描述格式：更清楚表達趨勢
                    if net_buy > 1000: 
                        foreign_msg = "💰外資大買"
                        foreign_display = f"連續買進 (近5日買超 {abs(int(net_buy))}張)"
                        foreign_score = 2.5 
                    elif net_buy < -1000:
                        foreign_msg = "💸外資提款"
                        foreign_display = f"連續倒貨 (近5日賣超 {abs(int(net_buy))}張)"
                        foreign_score = -2.5
                    elif net_buy > 0:
                        foreign_msg = "外資小買"
                        foreign_display = f"調節持股 (小幅買超)"
                        foreign_score = 0.5
                    else:
                        foreign_msg = "外資小賣"
                        foreign_display = f"調節持股 (小幅賣超)"
                        foreign_score = -0.5

            # 綜合評分
            latest = df.iloc[-1]
            close_price = latest['close']
            score = 5.0
            reasons = []
            
            score += foreign_score
            if foreign_msg != "外資中立": reasons.append(f"{foreign_msg}({int(net_buy)}張)")
            
            ma60 = latest['SMA_60'] if not pd.isna(latest['SMA_60']) else close_price
            if close_price > ma60:
                score += 1.5
                reasons.append("📈站上季線")
            else:
                score -= 1.5
                reasons.append("📉跌破季線")

            macd = latest['MACD'] if not pd.isna(latest['MACD']) else 0
            signal = latest['MACD_signal'] if not pd.isna(latest['MACD_signal']) else 0
            if macd > signal: reasons.append("🐂MACD金叉")
            else: reasons.append("🐻MACD死叉")
            
            rsi = latest['RSI_14'] if not pd.isna(latest['RSI_14']) else 50
            if rsi > 80: score -= 0.5; reasons.append("⚠️過熱")
            elif rsi < 20: score += 1.0; reasons.append("💎超賣")

            score = max(1, min(10, score))
            
            # 行動建議 + 對應樣式類別
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
            
            # ========== 多角色 AI 分析 (v13) ==========
            try:
                multi_role = MultiRoleAnalyzer()
                # 計算近5日價格變化
                price_5d_ago = df['close'].iloc[-5] if len(df) >= 5 else close_price
                price_change_5d = ((close_price - price_5d_ago) / price_5d_ago) * 100
                
                role_analysis = multi_role.analyze(
                    # 籌碼數據
                    foreign_net_volume=int(net_buy * 1000),  # 轉回張數
                    positive_days=3 if net_buy > 0 else 0,
                    # 技術數據
                    close=close_price,
                    ma60=ma60,
                    ma20=latest['SMA_60'] if not pd.isna(latest['SMA_60']) else close_price,  # 用60MA代替
                    rsi=rsi,
                    macd_diff=macd - signal,
                    price_change_5d=price_change_5d,
                    # 情境數據 (簡化處理)
                    has_positive_news=score >= 8,
                    has_negative_news=score <= 3,
                    sector_trend="up" if close_price > ma60 else "down",
                    market_sentiment="bullish" if score >= 6 else ("bearish" if score <= 4 else "neutral")
                )
            except Exception as role_err:
                print(f"⚠️ 多角色分析錯誤: {role_err}")
                role_analysis = None
            
            return {
                '代號': stock_id, '名稱': stock_name, '收盤價': close_price,
                '評分': round(score, 1), '建議': rec, '建議類別': rec_class,
                '外資動向': foreign_display, '詳細理由': " ".join(reasons),
                '分析日期': end_date,
                'reasons_raw': reasons, # 保留原始 list 供 AI 參考
                'chart_data': {
                    'chips': min(100, max(0, 50 + int(net_buy/20))), # 簡單正規化
                    'tech_ma': 80 if close_price > ma60 else 20,
                    'tech_macd': 80 if macd > signal else 20,
                    'tech_rsi': rsi,
                    'score': score * 10
                },
                'role_analysis': role_analysis  # 多角色分析結果
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ 分析錯誤: {e}")
            return None

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

    # Read from watchlist.json if exists, otherwise use hardcoded list
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            watchlist_data = json.load(f)
            my_portfolio = [(s["ticker"], s["name"]) for s in watchlist_data.get("stocks", [])]
            print(f"📋 已載入追蹤清單：{len(my_portfolio)} 檔股票")
    except FileNotFoundError:
        my_portfolio = [
            ("2330", "台積電"), ("2317", "鴻海"), ("0050", "元大台灣50"),
            ("0056", "元大高股息"), ("00919", "群益高股息"),
            ("1303", "南亞"), ("2603", "長榮"), ("2615", "萬海"),
            ("1609", "大亞"), ("3090", "日電貿"), ("6715", "嘉基"), ("1519", "華城"),
            ("3293", "鈊象"), ("5381", "合正"), ("8011", "台通"), ("4763", "材料-KY"),
            ("3265", "台星科"), ("2376", "技嘉"), ("2379", "瑞昱"), ("3034", "聯詠"),
            ("7749", "意騰-KY"), ("3035", "智原"), ("6197", "佳必琪"), ("3680", "家登"),
            ("3088", "艾訊"), ("6579", "研揚")
        ]
        print(f"⚠️ 使用預設追蹤清單：{len(my_portfolio)} 檔股票")
    
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
        res = ProAnalyzer.analyze_stock(dl, stock_id, stock_name)
        if res:
            excel_data.append(res)
            
            # 判斷是否觸發深度分析 (評分 >= 8 或 <= 3)
            if res['評分'] >= 8 or res['評分'] <= 3:
                icon = "🔥" if res['評分'] >= 8 else "💀"
                
                # 呼叫 Perplexity
                # 呼叫 Perplexity
                ai_search_result = ProAnalyzer.ask_perplexity(
                    stock_name, stock_id, res['評分'], res['詳細理由']
                )
                res['ai_insight'] = ai_search_result
                
                # 計算喵姆評分 (Miao-Mu Score)
                sentiment_bonus = 0
                # 放寬判定標準，支援有無括號的關鍵字
                if "正面" in ai_search_result: sentiment_bonus = 2
                elif "負面" in ai_search_result: sentiment_bonus = -2
                
                miao_score = round(res['評分'] + sentiment_bonus, 1)
                miao_score = max(1, min(10, miao_score)) # 限制在 1-10
                res['miao_score'] = miao_score
                
                # 更新 Chart Data (加入喵姆評分影響)
                res['chart_data']['score'] = miao_score * 10
                res['chart_data']['miao_score'] = miao_score # 額外儲存

                # 更新 Line 訊息
                line_msg += f"\n{'='*18}\n"
                line_msg += f"{icon} {res['名稱']}({res['代號']}) ${res['收盤價']}\n"
                line_msg += f"🐱 喵姆評分: {miao_score} (技術分:{res['評分']})\n"
                line_msg += f"📊 {res['詳細理由']}\n"
                line_msg += f"🤖 AI觀點: {ai_search_result}\n"
                line_msg += f"🔍 點此查看即時情報：https://www.perplexity.ai/search?q=分析{stock_name}{stock_id}今日動態\n"
                
                # 更新 Buffer 檔案內容
                buffer_content += f"【{stock_name} ({stock_id})】\n"
                buffer_content += f"- 喵姆評分: {miao_score} (技術分: {res['評分']})\n"
                buffer_content += f"- 收盤價: {res['收盤價']}\n"
                buffer_content += f"- 技術/籌碼訊號: {res['詳細理由']}\n"
                buffer_content += f"- Perplexity搜尋摘要: {ai_search_result}\n"
                buffer_content += "-" * 50 + "\n"
                
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
        df = pd.DataFrame(excel_data)
        if 'reasons_raw' in df.columns: del df['reasons_raw']
        if 'ai_insight' in df.columns: del df['ai_insight']  # 避免 Excel 太亂，AI 文字放 HTML
        
        df = df.sort_values(by='評分', ascending=False)
        filename = f"股市日報_{datetime.now().strftime('%Y%m%d')}.xlsx"
        df.to_excel(filename, index=False)
        print(f"\n✅ 成功建立 Excel 報表：{filename}")
        
        generate_index_html(excel_data)
        
    except Exception as e:
        print(f"❌ 報表儲存失敗: {e}")

def generate_index_html(data):
    """
    生成喵姆 AI 股市偵測站的互動式報表 (index.html)
    包含 Chart.js 雷達圖與 Tab 切換，雷達圖正中央顯示喵姆評分
    """
    date_str = datetime.now().strftime('%Y-%m-%d')
    json_data = json.dumps(data, ensure_ascii=False)
    
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
            /* 互動式追蹤清單側邊欄 */
            .sidebar {{
                position: fixed;
                right: 0;
                top: 0;
                width: 360px;
                height: 100%;
                background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
                transform: translateX(100%);
                transition: transform 0.3s ease;
                z-index: 100;
                border-left: 1px solid rgba(56, 189, 248, 0.2);
                box-shadow: -4px 0 20px rgba(0, 0, 0, 0.5);
            }}
            .sidebar.open {{
                transform: translateX(0);
            }}
            .sidebar-overlay {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                opacity: 0;
                visibility: hidden;
                transition: all 0.3s ease;
                z-index: 99;
            }}
            .sidebar-overlay.open {{
                opacity: 1;
                visibility: visible;
            }}
            .watchlist-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 16px;
                background: rgba(30, 41, 59, 0.8);
                border-radius: 10px;
                margin-bottom: 8px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.2s ease;
            }}
            .watchlist-item:hover {{
                background: rgba(56, 189, 248, 0.1);
                border-color: rgba(56, 189, 248, 0.3);
            }}
            .watchlist-btn {{
                cursor: pointer;
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.2s ease;
            }}
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
                   <button onclick="promptAdminLogin()" class="px-4 py-2 rounded-full bg-emerald-900/30 text-emerald-400 text-sm border border-emerald-800/50 backdrop-blur hover:bg-emerald-800/50 transition cursor-pointer" id="admin-btn">
                     🔐 管理後台
                   </button>
                </div>
            </header>
            
            <div id="cards-container" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            </div>
            
            <footer class="mt-12 text-center text-gray-600 text-sm">
                <p>Powered by Perplexity AI & FinMind | 本報告僅供參考，投資風險請自負 | 喵姆 AI 股市偵測站</p>
            </footer>
        </div>
        
        <!-- 互動式追蹤清單側邊欄 -->
        <div id="sidebar-overlay" class="sidebar-overlay" onclick="toggleSidebar()"></div>
        <div id="sidebar" class="sidebar p-6">
            <div class="flex justify-between items-center mb-6">
                <h3 class="text-xl font-bold text-white">📋 追蹤清單管理</h3>
                <button onclick="toggleSidebar()" class="text-gray-400 hover:text-white text-2xl transition">&times;</button>
            </div>
            
            <div class="mb-6">
                <p class="text-sm text-gray-400 mb-3">新增股票到追蹤清單，下次分析時會自動納入</p>
                <div class="flex gap-2">
                    <input id="new-ticker" type="text" placeholder="股票代號 (如 2330)" 
                           class="flex-1 px-4 py-3 bg-slate-800/80 border border-slate-600 rounded-xl text-white text-sm focus:border-cyan-500 focus:outline-none transition">
                    <input id="new-name" type="text" placeholder="名稱 (如 台積電)" 
                           class="flex-1 px-4 py-3 bg-slate-800/80 border border-slate-600 rounded-xl text-white text-sm focus:border-cyan-500 focus:outline-none transition">
                </div>
                <button onclick="addStock()" class="w-full mt-3 py-3 bg-gradient-to-r from-cyan-600 to-purple-600 hover:from-cyan-500 hover:to-purple-500 rounded-xl text-white font-medium transition shadow-lg">
                    ＋ 加入追蹤
                </button>
            </div>
            
            <div class="border-t border-slate-700 pt-4">
                <div class="flex justify-between items-center mb-3">
                    <span class="text-sm text-gray-400">目前追蹤中</span>
                    <span id="watchlist-count" class="text-sm text-cyan-400 font-medium">0 檔</span>
                </div>
                <div id="watchlist-items" class="max-h-[50vh] overflow-y-auto space-y-2 pr-2">
                    <!-- 動態生成 -->
                </div>
            </div>
            
            <div class="absolute bottom-6 left-6 right-6">
                <button onclick="saveWatchlistToFile()" class="w-full py-3 bg-emerald-600 hover:bg-emerald-500 rounded-xl text-white font-medium transition">
                    💾 儲存變更
                </button>
                <p class="text-xs text-gray-500 mt-2 text-center">儲存後重新執行 main.py 即可生效</p>
            </div>
        </div>

        <script>
            const stockData = {json_data};
            
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
                                    <div class="text-2xl font-mono mt-1 text-gray-200">$${{item['收盤價'].toFixed(2)}}</div>
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
                                        <span class="${{item['外資動向'].includes('-') ? 'text-red-400' : 'text-green-400'}} font-mono font-medium">${{item['外資動向']}}</span>
                                    </div>
                                    <div class="p-3 bg-gray-800/30 rounded-lg border border-gray-700/30 text-xs text-gray-300 leading-relaxed">
                                        ${{item['詳細理由']}}
                                    </div>
                                </div>
                            </div>
                            
                            <div id="view-ai-${{index}}" class="view-content hidden">
                                ${{item.role_analysis ? `
                                <!-- 衝突警示 -->
                                ${{item.role_analysis.conflict_intensity > 0.3 ? `
                                <div class="mb-3 p-3 bg-yellow-900/30 border border-yellow-600/50 rounded-xl">
                                    <span class="text-yellow-400 text-sm font-medium">⚠️ 訊號衝突 (強度: ${{(item.role_analysis.conflict_intensity * 100).toFixed(0)}}%)</span>
                                    <p class="text-yellow-200/80 text-xs mt-1">${{item.role_analysis.integration_reason}}</p>
                                </div>
                                ` : ''}}
                                
                                <!-- 雙層語言摘要 -->
                                <div class="mb-3 p-4 bg-gradient-to-br from-cyan-900/30 to-blue-900/30 rounded-xl border border-cyan-600/30">
                                    <p class="text-xs text-cyan-400 font-medium mb-1">🔰 人話版</p>
                                    <p class="text-gray-200 text-sm leading-relaxed">${{item.role_analysis.summary_human}}</p>
                                </div>
                                <div class="mb-3 p-4 bg-gradient-to-br from-purple-900/30 to-indigo-900/30 rounded-xl border border-purple-600/30">
                                    <p class="text-xs text-purple-400 font-medium mb-1">📊 專業版</p>
                                    <p class="text-gray-300 text-xs leading-relaxed">${{item.role_analysis.summary_professional}}</p>
                                </div>
                                
                                <!-- 各角色結論 -->
                                <div class="space-y-2 mb-3">
                                    ${{item.role_analysis.role_outputs.map(role => `
                                    <div class="p-3 bg-gray-800/50 rounded-lg border border-gray-700/50">
                                        <div class="flex justify-between items-center mb-1">
                                            <span class="text-sm font-medium text-white">${{role.role_name === '籌碼分析官' ? '📊' : role.role_name === '技術分析官' ? '📉' : role.role_name === '風險評估官' ? '⚠️' : '🌐'}} ${{role.role_name}}</span>
                                            <span class="text-xs px-2 py-1 rounded-full ${{role.role_conclusion === 'bullish' ? 'bg-green-900/50 text-green-400' : role.role_conclusion === 'bearish' ? 'bg-red-900/50 text-red-400' : 'bg-gray-700/50 text-gray-400'}}">
                                                ${{role.role_conclusion === 'bullish' ? '看多' : role.role_conclusion === 'bearish' ? '看空' : '中立'}} (${{role.confidence}}%)
                                            </span>
                                        </div>
                                        <div class="text-xs text-gray-400">${{role.key_evidence.slice(0, 2).join(' • ')}}</div>
                                    </div>
                                    `).join('')}}
                                </div>
                                ` : `
                                <div class="p-4 bg-gradient-to-br from-blue-900/20 to-purple-900/20 rounded-xl border border-blue-500/20 mb-4">
                                    <p class="text-xs font-semibold text-cyan-400 mb-2 uppercase tracking-wider">🤖 Perplexity AI 深度分析</p>
                                    <p class="text-gray-200 leading-relaxed text-sm">${{aiContent}}</p>
                                </div>
                                `}}
                                <a href="https://www.perplexity.ai/search?q=分析${{item['名稱']}}${{item['代號']}}今日動態" target="_blank" 
                                   class="block w-full text-center py-3 rounded-xl bg-gradient-to-r from-cyan-600/80 to-purple-600/80 hover:from-cyan-500 hover:to-purple-500 transition-all text-sm font-medium text-white shadow-lg">
                                    🔍 前往 Perplexity 深度追蹤
                                </a>
                            </div>
                        </div>
                    `;
                    container.appendChild(card);
                    
                    // Render Radar Chart with center Kirin Index
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
            }}

            function switchTab(index, tab) {{
                document.getElementById('view-data-' + index).classList.add('hidden');
                document.getElementById('view-ai-' + index).classList.add('hidden');
                document.getElementById('tab-data-' + index).classList.remove('active');
                document.getElementById('tab-ai-' + index).classList.remove('active');
                
                document.getElementById('view-' + tab + '-' + index).classList.remove('hidden');
                document.getElementById('tab-' + tab + '-' + index).classList.add('active');
            }}
            
            renderCards();
            
            // ========== 管理後台密碼驗證 ==========
            let isAdminLoggedIn = false;
            const ADMIN_PASSWORD = 'Aimyon';  // 密碼直接寫在這裡（你可以改）
            
            function promptAdminLogin() {{
                if (isAdminLoggedIn) {{
                    toggleSidebar();
                    return;
                }}
                
                const password = prompt('🔐 請輸入管理員密碼：');
                if (password === null) return;  // 取消
                
                if (password === ADMIN_PASSWORD) {{
                    isAdminLoggedIn = true;
                    document.getElementById('admin-btn').innerHTML = '📋 追蹤清單';
                    toggleSidebar();
                    alert('✅ 登入成功！');
                }} else {{
                    alert('❌ 密碼錯誤');
                }}
            }}
            
            // ========== 互動式追蹤清單功能 ==========
            let watchlist = [];
            
            // 初始化追蹤清單（從目前顯示的股票）
            function initWatchlist() {{
                watchlist = stockData.map(s => ({{ ticker: s['代號'], name: s['名稱'] }}));
                // 嘗試從 localStorage 載入追蹤清單
                const saved = localStorage.getItem('miaomuwatchlist');
                if (saved) {{
                    try {{
                        watchlist = JSON.parse(saved);
                    }} catch(e) {{}}
                }}
                renderWatchlist();
            }}
            
            function toggleSidebar() {{
                document.getElementById('sidebar').classList.toggle('open');
                document.getElementById('sidebar-overlay').classList.toggle('open');
            }}
            
            function renderWatchlist() {{
                const container = document.getElementById('watchlist-items');
                const countEl = document.getElementById('watchlist-count');
                container.innerHTML = '';
                countEl.textContent = watchlist.length + ' 檔';
                
                watchlist.forEach((stock, idx) => {{
                    const item = document.createElement('div');
                    item.className = 'watchlist-item';
                    item.innerHTML = `
                        <div>
                            <span class="text-white font-medium">${{stock.name}}</span>
                            <span class="text-gray-500 text-sm ml-2">${{stock.ticker}}</span>
                        </div>
                        <button onclick="removeStock(${{idx}})" class="text-red-400 hover:text-red-300 text-sm px-3 py-1 rounded-lg hover:bg-red-900/30 transition">
                            ✕ 移除
                        </button>
                    `;
                    container.appendChild(item);
                }});
            }}
            
            function addStock() {{
                const ticker = document.getElementById('new-ticker').value.trim();
                const name = document.getElementById('new-name').value.trim();
                
                if (!ticker || !name) {{
                    alert('請輸入股票代號和名稱');
                    return;
                }}
                
                // 檢查是否已存在
                if (watchlist.some(s => s.ticker === ticker)) {{
                    alert('此股票已在追蹤清單中');
                    return;
                }}
                
                watchlist.push({{ ticker, name }});
                localStorage.setItem('miaomuwatchlist', JSON.stringify(watchlist));
                renderWatchlist();
                
                // 清空輸入框
                document.getElementById('new-ticker').value = '';
                document.getElementById('new-name').value = '';
            }}
            
            function removeStock(idx) {{
                watchlist.splice(idx, 1);
                localStorage.setItem('miaomuwatchlist', JSON.stringify(watchlist));
                renderWatchlist();
            }}
            
            function saveWatchlistToFile() {{
                const data = {{
                    updated: new Date().toISOString(),
                    stocks: watchlist
                }};
                const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/json' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'watchlist.json';
                a.click();
                URL.revokeObjectURL(url);
                alert('✅ watchlist.json 已下載！\\n請將檔案放到 stock_analyzer 資料夾，執行 main.py 即可生效。');
            }}
            
            initWatchlist();
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