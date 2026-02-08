import pandas as pd
import numpy as np
from main import ProAnalyzer
from datetime import datetime, timedelta

def verify():
    print("🧪 正在驗證回測功能...")
    
    # 1. 建立模擬數據 (200 天)
    dates = [datetime.now() - timedelta(days=i) for i in range(200)]
    dates.reverse()
    
    # 模擬股價走勢
    close_prices = 100 + np.cumsum(np.random.randn(200))
    low_prices = close_prices - 2
    high_prices = close_prices + 2
    volumes = np.random.randint(1000, 5000, 200)
    
    df = pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': close_prices - 0.5,
        'close': close_prices,
        'max': high_prices,
        'min': low_prices,
        'Trading_Volume': volumes
    })
    
    # 2. 執行指標計算
    df = ProAnalyzer.calculate_indicators(df)
    
    # 3. 執行回測介入
    print("📡 啟動模擬回測任務...")
    results = ProAnalyzer.backtest_strategy(df, "測試股票")
    
    if results and "total_return" in results:
        print(f"✅ 驗證成功！")
        print(f"   - 總報酬率: {results['total_return']}%")
        print(f"   - 勝率: {results['win_rate']}%")
        print(f"   - 最大回撤: {results['max_drawdown']}%")
    else:
        print("❌ 驗證失敗：無回測數據。")

if __name__ == "__main__":
    verify()
