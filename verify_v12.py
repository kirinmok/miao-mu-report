
import os
from dotenv import load_dotenv
from FinMind.data import DataLoader
from modules.analyzer import analyze_stock
import json

# Setup
load_dotenv()
api_token = os.getenv("FINMIND_TOKEN")
dl = DataLoader()
dl.login_by_token(api_token)

# Test Target
stock_id = "2330"
stock_name = "台積電"

print(f"🔬 Testing v12.0 Analysis for {stock_name} ({stock_id})...")

# Run Analysis
packet = analyze_stock(dl, stock_id, stock_name)

if packet:
    print("\n✅ Analysis Successful!")
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    
    # Validation
    assert 'meta' in packet
    assert 'snapshot' in packet
    assert 'evidence' in packet
    assert 'logic' in packet
    assert 'risk_radar' in packet['snapshot']
    print("\n✅ Structure Verification Passed!")
else:
    print("\n❌ Analysis Failed (Returned None)")
