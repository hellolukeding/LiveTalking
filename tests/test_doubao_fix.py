#!/usr/bin/env python3
"""
测试豆包TTS修复后的功能
======================
"""

import asyncio
import copy
import gzip
import json
import os
import sys
import time
import uuid

import numpy as np
import websockets
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv(
    "DOUBAO_VOICE_ID") or "zh_female_xiaohe_uranus_bigtts"

print("=" * 60)
print("豆包TTS修复测试")
print("=" * 60)
print(f"AppID: {DOUBAO_APPID}")
print(f"Token: {DOUBAO_TOKEN[:20]}...")
print(f"VoiceID: {DOUBAO_VOICE_ID}")
print()


async def test_doubao_tts():
    """测试豆包TTS连接和音频生成"""

    # 配置
    _host = "openspeech.bytedance.com"
    api_url = f"wss://{_host}/api/v1/tts/ws_binary"

    # 测试文本
    test_text = "你好，世界！"

    print(f"🧪 测试文本: '{test_text}'")
    print(f"🔗 连接: {api_url}")
    print()

    # 构建请求 - 使用修复后的格式
    request_json = {
        "app": {
            "appid": DOUBAO_APPID,
            "token": DOUBAO_TOKEN,  # 关键修复：使用实际token值
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": str(uuid.uuid4())
        },
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
            "text": test_text,
            "text_type": "plain",
            "operation": "submit"
        }
    }

    print("📋 请求体:")
    print(json.dumps(request_json, indent=2, ensure_ascii=False))
    print()

    # 准备WebSocket请求
    default_header = bytearray(b'\x11\x10\x11\x00')
    payload_bytes = str.encode(json.dumps(request_json))
    payload_bytes = gzip.compress(payload_bytes)
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
    full_client_request.extend(payload_bytes)

    # 认证头
    header = {"Authorization": f"Bearer {DOUBAO_TOKEN}"}

    try:
        print("🔄 正在连接WebSocket...")
        async with websockets.connect(api_url, extra_headers=header, ping_interval=None, close_timeout=10) as ws:
            print("✅ WebSocket连接成功！")
            print()

            print("📤 发送请求...")
            await ws.send(full_client_request)
            print("✅ 请求已发送")
            print()

            print("⏳ 等待响应...")
            audio_data = []
            error_messages = []

            start_time = time.time()
            timeout = 10  # 10秒超时

            while time.time() - start_time < timeout:
                try:
                    # 设置超时接收
                    res = await asyncio.wait_for(ws.recv(), timeout=2.0)

                    # 解析响应
                    if len(res) >= 4:
                        header_size = res[0] & 0x0f
                        message_type = res[1] >> 4
                        flags = res[1] & 0x0f
                        payload = res[header_size*4:]

                        if message_type == 0xB:  # 音频响应
                            if flags != 0 and len(payload) >= 8:
                                seq_num = int.from_bytes(
                                    payload[:4], "big", signed=True)
                                audio_chunk = payload[8:]
                                if len(audio_chunk) > 0:
                                    audio_data.append(audio_chunk)
                                    print(
                                        f"🎵 收到音频块 {len(audio_data)}: {len(audio_chunk)} bytes")
                        elif message_type == 0xF:  # 错误响应
                            error_text = payload.decode(
                                'utf-8', errors='ignore')
                            error_messages.append(error_text)
                            print(f"❌ 错误: {error_text}")
                        elif message_type == 0xB and flags == 0:
                            print(
                                f"ℹ️  ACK消息 (序列号: {int.from_bytes(payload[:4], 'big', signed=True)})")

                except asyncio.TimeoutError:
                    if len(audio_data) > 0:
                        print("✅ 音频接收完成")
                        break
                    continue
                except Exception as e:
                    print(f"⚠️ 接收异常: {e}")
                    break

            # 分析结果
            print()
            print("=" * 60)
            print("📊 测试结果")
            print("=" * 60)

            if audio_data:
                # 合并所有音频数据
                full_audio = b''.join(audio_data)
                audio_array = np.frombuffer(full_audio, dtype=np.int16)

                print(f"✅ 成功！收到 {len(audio_data)} 个音频块")
                print(f"   总音频数据: {len(full_audio)} bytes")
                print(f"   音频样本数: {len(audio_array)}")
                print(f"   音频均值: {np.mean(audio_array):.2f}")
                print(
                    f"   音频范围: [{np.min(audio_array)}, {np.max(audio_array)}]")

                # 检查是否为静音
                if np.all(audio_array == 0):
                    print("   ⚠️  警告: 音频数据全为零（可能是静音）")
                else:
                    print("   🎉 音频数据有效！")

                return True
            elif error_messages:
                print("❌ 测试失败 - 收到错误响应")
                for error in error_messages:
                    print(f"   错误: {error}")
                return False
            else:
                print("❌ 测试失败 - 未收到任何响应")
                return False

    except Exception as e:
        print(f"❌ 连接或请求失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("开始豆包TTS修复测试...")
    print()

    # 检查环境变量
    if not all([DOUBAO_APPID, DOUBAO_TOKEN]):
        print("❌ 缺少必要的环境变量！")
        print("请检查 .env 文件中的 DOUBAO_APPID 和 DOUBAO_TOKEN")
        return

    success = await test_doubao_tts()

    print()
    if success:
        print("🎉 测试通过！豆包TTS修复成功。")
        print()
        print("建议:")
        print("1. 重启 LiveTalking 服务")
        print("2. 测试实际对话功能")
        print("3. 监控日志确认音频流正常")
    else:
        print("❌ 测试失败，请检查:")
        print("1. 网络连接")
        print("2. 火山引擎服务状态")
        print("3. AppID、Token和VoiceID是否正确")
        print("4. 账户余额和服务开通状态")

if __name__ == "__main__":
    asyncio.run(main())
