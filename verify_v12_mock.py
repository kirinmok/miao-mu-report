
import pandas as pd
from datetime import datetime
from modules.analyzer import analyze_stock
import json

class MockDataLoader:
    def login_by_token(self, token):
        pass

    def taiwan_stock_daily(self, stock_id, start_date, end_date):
        # Create dummy price data (rising trend)
        dates = pd.date_range(start=start_date, end=end_date)
        data = {
            'date': dates,
            'close': [100 + i + (i%5)*2 for i in range(len(dates))],
            'open': [100 + i for i in range(len(dates))],
            'max': [105 + i for i in range(len(dates))],
            'min': [95 + i for i in range(len(dates))],
            'Trading_Volume': [5000 for _ in range(len(dates))]
        }
        return pd.DataFrame(data)

    def taiwan_stock_institutional_investors(self, stock_id, start_date, end_date):
        # Create dummy foreign investor data (accumulating)
        dates = pd.date_range(start=start_date, end=end_date)
        data = []
        for d in dates:
            data.append({'date': d, 'name': 'Foreign_Investor', 'buy': 2000, 'sell': 500})
            data.append({'date': d, 'name': 'Investment_Trust', 'buy': 100, 'sell': 500})
        return pd.DataFrame(data)

# Run Mock Test
print("🔬 Running Mock Verification for v12.0 Logic...")
mock_dl = MockDataLoader()
packet = analyze_stock(mock_dl, "TEST", "測試股")

if packet:
    print("\n✅ Mock Analysis Successful!")
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    
    # Logic Checks
    s = packet['snapshot']
    print(f"\nHuman Summary: {s['human_summary']}")
    print(f"Risk Radar: {s['risk_radar']}")
    
    assert packet['evidence']['foreign']['tag'] == "ACCUMULATING"
    assert s['action'] in ["強力買進", "偏多操作", "觀望", "保留", "賣出"]
    assert s['action_class'] in ["action-buy", "action-bullish", "action-hold", "action-caution", "action-sell"]
    assert 1 <= s['score'] <= 10
    print("\n✅ Logic Verification Passed!")
else:
    print("\n❌ Mock Analysis Failed")
