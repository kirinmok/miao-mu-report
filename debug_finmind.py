
import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("FINMIND_TOKEN")
url = "https://api.finmindtrade.com/api/v4/data"
parameter = {
    "dataset": "TaiwanStockPrice",
    "data_id": "2330",
    "start_date": "2024-01-01",
    "token": token
}

r = requests.get(url, params=parameter)
print(f"Status Code: {r.status_code}")
try:
    data = r.json()
    print("Response Keys:", data.keys())
    if 'msg' in data:
        print("Message:", data['msg'])
    if 'data' not in data:
        print("❌ 'data' field missing!")
        print("Full Response:", data)
    else:
        print(f"✅ Data found, records: {len(data['data'])}")
except Exception as e:
    print(f"JSON Decode Error: {e}")
    print(r.text)
