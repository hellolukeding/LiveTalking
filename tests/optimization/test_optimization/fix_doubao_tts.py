#!/usr/bin/env python3
"""
修复Doubao TTS问题
"""
import asyncio
import gzip
import json
import os
import uuid

import numpy as np
import websockets
from dotenv import load_dotenv

load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv("DOUBAO_VOICE_ID")

print(f"=== Doubao TTS 配置 ===")
print(f"AppID: {DOUBAO_APPID}")
print(f"Token: {DOUBAO_TOKEN[:20]}..." if DOUBAO_TOKEN else "None")
print(f"Voice ID: {DOUBAO_VOICE_ID}")


async def test_doubao_connection():
    """测试Doubao连接并查看返回的错误信息"""
    print(f"\n=== 测试Doubao连接 ===")

    _host = "openspeech.bytedance.com"
    api_url = f"wss://{_host}/api/v1/tts/ws_binary"

    # 创建请求
    request_json = {
        "app": {
            "appid": DOUBAO_APPID,
            "token": "access_token",
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test_user"
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
            "text": "你好，这是一个测试。",
            "text_type": "plain",
            "operation": "submit"
        }
    }

    # 准备请求数据
    default_header = bytearray(b'\x11\x10\x11\x00')
    payload_bytes = str.encode(json.dumps(request_json))
    payload_bytes = gzip.compress(payload_bytes)
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
    full_client_request.extend(payload_bytes)

    # WebSocket连接
    header = {"Authorization": f"Bearer {DOUBAO_TOKEN}"}

    try:
        print(f"正在连接: {api_url}")
        async with websockets.connect(api_url, extra_headers=header, ping_interval=None, close_timeout=10) as ws:
            print("✅ WebSocket连接成功")

            print("发送请求...")
            await ws.send(full_client_request)

            print("等待响应...")
            response_count = 0

            while True:
                try:
                    res = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    header_size = res[0] & 0x0f
                    message_type = res[1] >> 4
                    message_type_specific_flags = res[1] & 0x0f
                    payload = res[header_size*4:]

                    response_count += 1
                    print(f"\n📦 响应 {response_count}:")
                    print(f"   消息类型: 0x{message_type:X}")
                    print(f"   标志: {message_type_specific_flags}")
                    print(f"   载荷大小: {len(payload)} bytes")

                    if len(payload) > 0:
                        try:
                            # 尝试解析为JSON（可能是错误信息）
                            payload_str = payload.decode('utf-8')
                            print(f"   载荷内容: {payload_str}")

                            if payload_str.startswith('{'):
                                json_data = json.loads(payload_str)
                                print(f"   JSON解析: {json_data}")
                        except:
                            # 如果不是JSON，显示为二进制数据
                            print(f"   二进制数据: {payload[:50]}...")

                    if message_type == 0xb:  # audio-only server response
                        if message_type_specific_flags == 0:
                            print("   → ACK消息（无音频数据）")
                            continue
                        else:
                            sequence_number = int.from_bytes(
                                payload[:4], "big", signed=True)
                            payload_size = int.from_bytes(
                                payload[4:8], "big", signed=False)
                            audio_data = payload[8:]

                            print(f"   → 音频数据，序列号: {sequence_number}")
                            print(f"   → 音频数据大小: {len(audio_data)} bytes")

                            if len(audio_data) > 0:
                                audio_array = np.frombuffer(
                                    audio_data, dtype=np.int16)
                                print(f"   → 音频数组形状: {audio_array.shape}")
                                print(
                                    f"   → 音频范围: [{np.min(audio_array)}, {np.max(audio_array)}]")
                                print(
                                    f"   → 音频平均值: {np.mean(audio_array):.2f}")
                                print(f"   → 是否全零: {np.all(audio_array == 0)}")

                            if sequence_number < 0:
                                print("   → 传输结束")
                                break
                    else:
                        print(f"   → 非音频消息，忽略")
                        break

                except asyncio.TimeoutError:
                    print("❌ 等待响应超时")
                    break
                except Exception as e:
                    print(f"❌ 接收数据时出错: {e}")
                    break

            if response_count == 0:
                print("❌ 没有收到任何响应")
                return False
            else:
                print(f"\n✅ 总共收到 {response_count} 个响应")
                return True

    except Exception as e:
        print(f"❌ WebSocket连接失败: {e}")
        return False


def test_voice_type_formats():
    """测试不同的voice type格式"""
    print(f"\n=== 测试不同Voice Type格式 ===")

    base_formats = [
        DOUBAO_VOICE_ID,  # 原始格式
        f"{DOUBAO_APPID}.{DOUBAO_VOICE_ID}",  # 带AppID
        f"volcano_tts.{DOUBAO_VOICE_ID}",  # 带集群
        f"zh_female_{DOUBAO_VOICE_ID}",  # 补全前缀
        "zh_female_xiaohe_uranus_bigtts",  # 完整格式
        "zh_female_xiaoyu_uranus_bigtts",  # 另一个语音
        "zh_male_xiaoyu_uranus_bigtts",  # 男性语音
    ]

    print("可能的voice type格式:")
    for i, fmt in enumerate(base_formats, 1):
        print(f"{i}. {fmt}")

    return base_formats


if __name__ == "__main__":
    print("Doubao TTS 诊断和修复工具")
    print("=" * 60)

    if not all([DOUBAO_APPID, DOUBAO_TOKEN, DOUBAO_VOICE_ID]):
        print("❌ 缺少必要的环境变量")
        exit(1)

    # 1. 测试当前配置
    result = asyncio.run(test_doubao_connection())

    if not result:
        print("\n" + "=" * 60)
        print("当前配置失败，尝试不同的voice type格式...")

        # 2. 测试不同格式
        formats = test_voice_type_formats()

        # 3. 建议解决方案
        print("\n" + "=" * 60)
        print("💡 建议解决方案:")
        print("\n1. 检查Doubao API凭证:")
        print("   - 登录火山引擎控制台")
        print("   - 检查AppID和Token是否有效")
        print("   - 确认语音服务是否开通")

        print("\n2. 尝试更新环境变量:")
        print("   - DOUBAO_TOKEN可能已过期")
        print("   - 重新获取API凭证")

        print("\n3. 检查Voice ID格式:")
        print("   - 参考火山引擎文档")
        print("   - 尝试不同的语音类型")

        print("\n4. 备用方案:")
        print("   - 配置腾讯TTS")
        print("   - 配置Azure TTS")
        print("   - 使用本地TTS服务")
    else:
        print("\n🎉 Doubao TTS连接正常！")
