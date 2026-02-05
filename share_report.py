#!/usr/bin/env python3
"""
喵姆 AI 股市偵測站 - 報表分享工具
使用 ngrok 將本機報表臨時分享給外部存取
"""
import os
import sys
import threading
import http.server
import socketserver
from pyngrok import ngrok

# 設定
PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """安靜版 HTTP Handler，減少終端機輸出"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        # 只記錄重要請求
        if "index.html" in str(args):
            print(f"📥 有人存取了報表")

def start_server():
    """啟動本地 HTTP 伺服器"""
    with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
        httpd.serve_forever()

def main():
    print("\n" + "="*50)
    print("🐱 喵姆 AI 股市偵測站 - 報表分享工具")
    print("="*50 + "\n")
    
    # 檢查 index.html 是否存在
    index_path = os.path.join(DIRECTORY, "index.html")
    if not os.path.exists(index_path):
        print("❌ 錯誤：找不到 index.html！")
        print("   請先執行 python3 main.py 產生報表。")
        sys.exit(1)
    
    print(f"📁 分享目錄：{DIRECTORY}")
    print(f"🔧 本地埠號：{PORT}")
    print("⏳ 正在啟動伺服器...")
    
    # 在背景執行 HTTP 伺服器
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"✅ 本地伺服器已啟動：http://localhost:{PORT}")
    
    # 啟動 ngrok 通道
    print("⏳ 正在建立 ngrok 通道...")
    try:
        public_url = ngrok.connect(PORT, "http")
        print("\n" + "="*50)
        print("🎉 分享成功！請將以下網址傳給對方：")
        print("="*50)
        print(f"\n   👉 {public_url}\n")
        print("="*50)
        print("\n⚠️  重要提醒：")
        print("   • 此網址為臨時網址，每次啟動都會不同")
        print("   • 關閉此程式（Ctrl+C）即代表中斷分享")
        print("   • 對方只能看到 index.html 報表內容")
        print("   • ngrok 免費版有頻寬限制，適合短期分享")
        print("\n💡 按下 Ctrl+C 即可停止分享\n")
        
        # 保持程式運行
        try:
            while True:
                pass
        except KeyboardInterrupt:
            pass
            
    except Exception as e:
        print(f"❌ ngrok 啟動失敗：{e}")
        print("\n💡 如果是首次使用，可能需要設定 ngrok authtoken：")
        print("   1. 前往 https://dashboard.ngrok.com/signup 註冊")
        print("   2. 複製 authtoken")
        print("   3. 執行：ngrok config add-authtoken <YOUR_TOKEN>")
        sys.exit(1)
    
    finally:
        print("\n🛑 正在關閉分享...")
        ngrok.kill()
        print("✅ 已停止分享，再見！\n")

if __name__ == "__main__":
    main()
