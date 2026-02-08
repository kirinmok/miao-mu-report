#!/bin/bash
# 啟動喵姆 AI 戰情室伺服器

# 1. 檢查並安裝套件
if ! python3 -c "import flask" &> /dev/null; then
    echo "📦 安裝必要套件..."
    pip install -r requirements.txt
fi

# 2. 檢查是否已有 index.html，沒有則先跑一次 main.py 生成
if [ ! -f "index.html" ]; then
    echo "⚠️ 尚未生成 index.html，正在執行初次分析..."
    python3 main.py
fi

# 3. 啟動伺服器
echo "🚀 啟動戰情室伺服器..."
python3 server.py
