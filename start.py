#!/usr/bin/env python3
"""启动脚本：自动创建 ngrok 隧道 + 启动 Flask 服务"""
import os
import sys
import threading
import time
from dotenv import load_dotenv

load_dotenv()

NGROK_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "")
os.environ["NGROK_AUTHTOKEN"] = NGROK_TOKEN  # pyngrok reads this

# 启动 Flask（先 import 触发 pyngrok）
print("=" * 50)
print("  DeepSeek 企业微信聊天机器人")
print("=" * 50)

# 设置 ngrok
from pyngrok import ngrok, conf
conf.get_default().auth_token = NGROK_TOKEN

# 连接 ngrok 隧道
try:
    tunnel = ngrok.connect(5000, "http")
    public_url = tunnel.public_url
    print(f"\n  ngrok 公网地址: {public_url}")
    print(f"  回调地址:     {public_url}/callback\n")
except Exception as e:
    print(f"\n  ngrok 连接失败: {e}")
    print("  将以本地模式启动...\n")
    public_url = None

# 启动 Flask 服务
print("  启动 Flask 服务...\n")
from main import app
app.run(host="0.0.0.0", port=5000, debug=False)
