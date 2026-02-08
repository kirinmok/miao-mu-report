import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def ask_perplexity(stock_name, stock_id, risk_summary, behavior_desc, api_key):
    """
    [Logic Layer] 呼叫 Perplexity API 進行深度辯證 (3分鐘層級)
    """
    if not api_key:
        return "[無 API Key] 無法進行深度辯證"

    print(f"🤖 AI 正在進行深度辯證: {stock_name}...")
    
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = "你是一位極度理性的風險控制官。請根據提供的數據，用批判性角度分析該股票的風險與機會。禁止給出買賣建議。請分別列出【風險警示】與【潛在機會】。"
    user_content = f"股票：{stock_name} ({stock_id})\n風險狀態：{risk_summary}\n籌碼行為：{behavior_desc}\n請分析其背後的邏輯與陷阱。"

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

def ask_ai_custom(query, stock_name, stock_id, api_key):
    """
    [Interact] 使用者自訂提問 (Dynamic Q&A)
    """
    if not api_key:
        return "<p class='text-red-400'>❌ 系統未設定 API Key</p>"

    print(f"💬 AI 回答提問: {stock_name} - {query}...")
    
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"你是一一位專業的台股分析師。正在分析 {stock_name} ({stock_id})。請針對使用者的提問提供專業、數據佐證的回答。回答請使用 HTML 格式 (可使用 <b>, <ul>, <li>, <p> 等標籤)，不需完整的 html/body。"
    
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            # 簡單清洗 Markdown 標記，避免格式跑掉
            content = content.replace("```html", "").replace("```", "")
            return content
        else:
            return f"<p class='text-red-400'>❌ API Error: {response.status_code}</p>"
    except Exception as e:
        return f"<p class='text-red-400'>❌ 連線錯誤: {e}</p>"

def calculate_indicators(df):
    """
    [Analysis Core] 計算技術指標
    """
    df = df.sort_values('date')
    close = df['close']

    # MA
    df['SMA_60'] = close.rolling(window=60).mean()
    df['SMA_20'] = close.rolling(window=20).mean()

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

def analyze_foreign_behavior(df_foreign):
    """
    [Behavior Classifier] 判讀外資行為
    """
    if df_foreign.empty:
        return "NO_DATA", "無外資數據"
    
    last_5_days = df_foreign.tail(5)
    net_buys = last_5_days['buy'] - last_5_days['sell']
    
    # 簡單行為邏輯
    total_net = net_buys.sum() // 1000
    positive_days = (net_buys > 0).sum()
    
    if total_net > 5 and positive_days >= 4:
        return "ACCUMULATING", f"連續吃貨 (近5日買超 {int(total_net)}張)"
    elif total_net < -5 and positive_days <= 1:
        return "DUMPING", f"連續倒貨 (近5日賣超 {abs(int(total_net))}張)"
    elif total_net > 0:
        return "HOLDING", "外資觀望 (小幅買超)"
    else:
        return "ADJUSTING", "調節持股 (小幅賣超)"

def calculate_risk_radar(latest, chip_status):
    """
    [Risk Engine] 計算風險雷達數值 (0-100)
    """
    risks = {
        'tech_overheat': 50,      # 技術過熱
        'chip_instability': 50,   # 籌碼不穩
        'trend_weakness': 50      # 趨勢疲弱
    }
    
    # 1. 技術過熱 (RSI)
    rsi = latest.get('RSI_14', 50)
    if rsi > 70: risks['tech_overheat'] = 80 + (rsi - 70)
    elif rsi < 30: risks['tech_overheat'] = 20 # 超賣反而風險低（機會高）
    else: risks['tech_overheat'] = 50
    
    # 2. 籌碼不穩
    if chip_status == "DUMPING": risks['chip_instability'] = 90
    elif chip_status == "ACCUMULATING": risks['chip_instability'] = 20
    else: risks['chip_instability'] = 50
    
    # 3. 趨勢疲弱 (股價 vs 季線)
    close = latest['close']
    ma60 = latest.get('SMA_60', close)
    if close < ma60: risks['trend_weakness'] = 80 # 破線風險高
    else: risks['trend_weakness'] = 30 # 站上季線風險低
    
    return risks

def get_action_recommendation(score):
    """
    [Action Badge Mapper] 根據評分決定行動建議
    """
    if score >= 9:
        return "強力買進", "action-buy"
    elif score >= 7:
        return "偏多操作", "action-bullish"
    elif score >= 4:
        return "觀望", "action-hold"
    elif score >= 2:
        return "保留", "action-caution"
    else:
        return "賣出", "action-sell"

def get_human_summary(name, risks, behavior_desc, behavior_tag):
    """
    [Humanizer] 產生一句話結論 + 評分 + 行動建議
    """
    # 計算評分 (風險越高分數越低)
    avg_risk = sum(risks.values()) / len(risks)
    score = int(max(1, min(10, 10 - (avg_risk / 10))))  # 0-100 risk -> 10-1 score
    
    # 調整：籌碼面強勢加分
    if behavior_tag == "ACCUMULATING":
        score = min(10, score + 2)
    elif behavior_tag == "DUMPING":
        score = max(1, score - 2)
    
    # 決定行動建議
    action, action_class = get_action_recommendation(score)
    
    # 生成摘要
    max_risk = max(risks, key=risks.get)
    risk_val = risks[max_risk]
    
    summary = f"{name} 目前{behavior_desc}。"
    
    if risk_val >= 80:
        if max_risk == 'tech_overheat': summary += "技術面嚴重過熱，慎防回檔。"
        elif max_risk == 'chip_instability': summary += "籌碼面鬆動，風險極高。"
        elif max_risk == 'trend_weakness': summary += "技術面已轉弱，上方壓力重重。"
    elif risk_val <= 30:
        summary += "風險指標偏低，具潛在機會。"
    else:
        summary += "多空力道膠著，建議持續觀察。"
        
    return score, action, action_class, summary

def analyze_stock(dl, stock_id, stock_name, perplexity_api_key=None):
    """
    [Controller] 核心分析入口，組裝 StockDecisionPacket
    """
    print(f"🚀 [v12.0 Risk Core] 分析中: {stock_name} ({stock_id})...")
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
        
        # 1. 獲取數據
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
        if df.empty: return None

        df = calculate_indicators(df)
        df_chips = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
        
        # 2. 核心運算
        latest = df.iloc[-1]
        
        # Behavior
        df_foreign = df_chips[df_chips['name'] == 'Foreign_Investor'] if not df_chips.empty else pd.DataFrame()
        behavior_tag, behavior_desc = analyze_foreign_behavior(df_foreign)
        
        # Risk Radar
        radar = calculate_risk_radar(latest, behavior_tag)
        
        # Human Summary + Action Badge
        score, action, action_class, summary = get_human_summary(stock_name, radar, behavior_desc, behavior_tag)
        
        # 3. 組裝 Packet
        packet = {
            "meta": { 
                "ticker": str(stock_id), 
                "name": str(stock_name), 
                "date": str(end_date),
                "close": float(latest['close']) 
            },
            
            # Layer 1: Snapshot (5s)
            "snapshot": {
                "action": str(action),              # 強力買進/偏多操作/觀望/保留/賣出
                "action_class": str(action_class),  # CSS class
                "score": int(score),                # 1-10 評分
                "risk_radar": {k: int(v) for k, v in radar.items()},
                "human_summary": str(summary),
                # 相容舊版欄位
                "評分": int(score),
                "建議": str(action),
                "建議類別": str(action_class),
                "詳細理由": str(summary)
            },
            
            # Layer 2: Evidence (30s)
            "evidence": {
                "foreign": {
                    "tag": str(behavior_tag),
                    "desc": str(behavior_desc)
                },
                "technical": {
                    "rsi": float(round(latest.get('RSI_14', 50), 1)),
                    "macd_diff": float(round(latest.get('MACD', 0) - latest.get('MACD_signal', 0), 2))
                }
            },
            
            # Layer 3: Logic (3m) - 僅在觸發時運算
            "logic": {
                "ai_analysis": ""
            }
        }
        
        # AI Logic Trigger (高風險或機會時觸發)
        # action: 強力買進/偏多操作/觀望/保留/賣出
        should_trigger_ai = action in ["強力買進", "賣出"]
        if perplexity_api_key and should_trigger_ai:
            ai_text = ask_perplexity(stock_name, stock_id, summary, behavior_desc, perplexity_api_key)
            packet['logic']['ai_analysis'] = ai_text
            # 相容舊版
            packet['ai_insight'] = ai_text
            
        return packet
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 分析錯誤: {e}")
        return None
