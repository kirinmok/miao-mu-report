import os
import json
import requests
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
LINE_CHANNEL_TOKEN = os.getenv("LINE_TOKEN")
YOUR_USER_ID = os.getenv("USER_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def send_line_push(msg):
    if not LINE_CHANNEL_TOKEN or not YOUR_USER_ID: 
        print("⚠️ LINE Token 未設定")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"}
    payload = {"to": YOUR_USER_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        requests.post(url, headers=headers, json=payload)
        print("✅ LINE 策略報告已發送")
    except Exception as e:
        print(f"❌ LINE 發送失敗: {e}")

def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        return "⚠️ 未設定 GEMINI_API_KEY，無法進行 AI 分析。"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini 思考失敗: {e}"

def main():
    print(f"\n🌙 啟動夜間策略會議 {datetime.now().strftime('%Y-%m-%d %H:%M')}...")

    # 1. 讀取今日數據與投資組合
    try:
        with open("daily_analysis.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        with open("portfolio.json", "r", encoding="utf-8") as f:
            portfolio = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到數據檔 (daily_analysis.json 或 portfolio.json)，請確認檔案存在。")
        return

    # 2. 篩選高信心的股票
    targets = [s for s in data if s['評分'] >= 7.5 or s['評分'] <= 3.5]
    
    if not targets:
        print("今日無顯著標的。")
        send_line_push("👵 阿嬤晚安：今天股市沒什麼特別的，明天我們休息觀察就好，不用急著動作喔！")
        return

    # 3. 準備資料給 AI
    stocks_info = []
    for s in targets:
        info = f"""
        【{s['名稱']} ({s['代號']})】
        - 現價: {s['收盤價']} (評分: {s['評分']})
        - 訊號: {s['詳細理由']}
        - 籌碼: 投信 {s.get('投信動向', 0)} 張, 外資 {s.get('外資動向', 0)} 張
        - 營收: {s.get('營收表現', 'N/A')}
        - AI 預測摘要: {s.get('ai_insight', '無')}
        """
        stocks_info.append(info)
    
    stock_context = "\n".join(stocks_info)
    portfolio_context = f"目前可用現金: {portfolio['cash_position']} 元\n持股明細: {json.dumps(portfolio['current_holdings'], ensure_ascii=False)}"

    # 4. 呼叫 Gemini (阿嬤流 Prompt)
    system_prompt = f"""
    你現在是華爾街最頂尖的操盤團隊。請根據以下數據，擬定一份「明天開盤的操作劇本」。
    
    【分析對象】
    {stock_context}
    
    【目前的投資組合】
    {portfolio_context}

    【重要要求】：
    1. **對象是 80 歲阿嬤**：完全不要用術語，請用最白話的方式講（例如：這檔已經賺夠了，我們落袋為安）。
    2. **針對持股給建議**：如果分析標的中包含已經持有的股票，請明確告訴阿嬤要「續抱」、「加碼」還是「賣掉」。
    3. **格式規定**：
       - **股票名稱** (動作：買進/賣出/看戲)
       - 👉 **怎麼做**：(例如：明天如果開高就買，開低就跑)
       - 💡 **為什麼**：(一句話解釋理由)
    3. **總結**：最後給阿嬤一句叮嚀。
    
    請直接輸出 LINE 訊息內容，不要有 Markdown 符號。
    """

    print("🧠 AI 正在分析劇本...")
    final_advice = ask_gemini(system_prompt)

    if final_advice:
        print("✅ 策略已生成")
        line_msg = f"👵 【阿嬤的股市小紙條】\n📅 {datetime.now().strftime('%Y-%m-%d')}\n\n{final_advice}\n\n🤖 喵姆 AI 團隊敬上"
        send_line_push(line_msg)

if __name__ == "__main__":
    main()
