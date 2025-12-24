#!/usr/bin/env python3
"""测试 Doubao TTS v1 API (Bearer Token 方式)"""
import os
import json
import uuid
import gzip
import time
from dotenv import load_dotenv

load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv("DOUBAO_VOICE_ID", "zh_female_vv_uranus_bigtts")

print("=" * 60)
print("测试 Doubao TTS v1 API (Bearer Token)")
print("=" * 60)
print(f"APPID: {DOUBAO_APPID}")
print(f"TOKEN: {DOUBAO_TOKEN[:30] if DOUBAO_TOKEN else 'None'}...")
print(f"VOICE_ID: {DOUBAO_VOICE_ID}")

if not DOUBAO_TOKEN:
    print("❌ 缺少 DOUBAO_TOKEN")
    exit(1)

import websocket

api_url = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
print(f"\n连接到: {api_url}")

# v1 API 使用 Bearer Token
header = {"Authorization": f"Bearer {DOUBAO_TOKEN}"}
print(f"Header: Authorization: Bearer {DOUBAO_TOKEN[:20]}...")

try:
    ws = websocket.create_connection(api_url, timeout=10, header=header)
    print("✅ WebSocket 连接成功!")
except Exception as e:
    print(f"❌ 连接失败: {e}")
    exit(1)

# 构建请求
request_json = {
    "app": {
        "appid": DOUBAO_APPID,
        "token": "access_token",
        "cluster": "volcano_tts"
    },
    "user": {"uid": "test_user"},
    "audio": {
        "voice_type": DOUBAO_VOICE_ID,
        "encoding": "pcm",
        "rate": 16000,
        "speed_ratio": 1.0,
        "volume_ratio": 1.0,
        "pitch_ratio": 1.0,
    },
    "request": {
        "reqid": str(uuid.uuid4()),
        "text": "你好，这是测试。",
        "text_type": "plain",
        "operation": "submit"
    }
}

print(f"\n发送请求...")
default_header = bytearray(b'\x11\x10\x11\x00')
payload_bytes = json.dumps(request_json).encode('utf-8')
payload_bytes = gzip.compress(payload_bytes)
full_request = bytearray(default_header)
full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
full_request.extend(payload_bytes)

ws.send_binary(bytes(full_request))
print("✅ 请求已发送")

# 接收响应
print("\n接收响应...")
ws.settimeout(30.0)
chunk_count = 0
total_bytes = 0
start_time = time.time()

while True:
    try:
        result = ws.recv()
        if not isinstance(result, bytes) or len(result) < 4:
            print(f"无效数据: {type(result)}")
            break
        
        header_size = (result[0] & 0x0f) * 4
        msg_type = (result[1] >> 4) & 0x0f
        flags = result[1] & 0x0f
        payload = result[header_size:] if len(result) > header_size else b''
        
        if msg_type == 0xb:  # 音频响应
            if flags == 0:
                continue  # ACK
            if len(payload) >= 8:
                seq = int.from_bytes(payload[:4], "big", signed=True)
                audio = payload[8:]
                chunk_count += 1
                total_bytes += len(audio)
                if chunk_count == 1:
                    print(f"✅ 收到第一个音频块，延迟: {time.time()-start_time:.3f}s")
                if seq < 0:
                    print("传输结束")
                    break
        elif msg_type == 0xf:  # 错误
            try:
                if len(payload) >= 8:
                    code = int.from_bytes(payload[:4], "big")
                    msg = gzip.decompress(payload[8:]).decode('utf-8')
                    print(f"❌ 错误 (code={code}): {msg}")
                else:
                    print(f"❌ 错误: {payload}")
            except:
                print(f"❌ 错误: {payload[:100]}")
            break
        else:
            print(f"未知消息类型: 0x{msg_type:X}")
            break
    except websocket.WebSocketTimeoutException:
        print("超时")
        break
    except Exception as e:
        print(f"错误: {e}")
        break

ws.close()
print(f"\n总计: {chunk_count} 个音频块, {total_bytes} 字节")
if chunk_count > 0:
    print("✅ v1 API 测试成功!")
else:
    print("❌ v1 API 测试失败")
