#!/usr/bin/env python3
"""
修复Doubao TTS问题 - 解码错误信息
"""
import asyncio
import gzip
import json
import os
import struct
import uuid

import numpy as np
import websockets
from dotenv import load_dotenv

load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv("DOUBAO_VOICE_ID")


async def decode_error_message():
    """解码Doubao返回的错误信息"""
    print(f"=== 解码Doubao错误信息 ===")

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
        async with websockets.connect(api_url, extra_headers=header, ping_interval=None, close_timeout=10) as ws:
            print("✅ WebSocket连接成功")

            await ws.send(full_client_request)
            print("请求已发送")

            # 接收所有响应
            responses = []
            while True:
                try:
                    res = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    responses.append(res)
                except asyncio.TimeoutError:
                    break

            print(f"\n收到 {len(responses)} 个响应")

            for i, res in enumerate(responses):
                print(f"\n📦 响应 {i+1}:")
                print(f"   原始数据长度: {len(res)} bytes")
                print(f"   原始数据: {res[:100]}")

                # 解析消息头
                if len(res) >= 4:
                    header_size = res[0] & 0x0f
                    message_type = res[1] >> 4
                    flags = res[1] & 0x0f

                    print(f"   Header size: {header_size}")
                    print(f"   Message type: 0x{message_type:X}")
                    print(f"   Flags: {flags}")

                    payload = res[header_size*4:]
                    print(f"   Payload length: {len(payload)}")

                    if len(payload) > 0:
                        # 尝试多种解码方式
                        print(f"   Payload (hex): {payload[:50].hex()}")

                        # 1. 尝试UTF-8解码
                        try:
                            text = payload.decode('utf-8')
                            print(f"   UTF-8文本: {text}")

                            # 如果是JSON，解析它
                            if text.startswith('{'):
                                try:
                                    json_data = json.loads(text)
                                    print(
                                        f"   JSON解析: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
                                except:
                                    pass
                        except:
                            print(f"   不是UTF-8文本")

                        # 2. 尝试解压（如果是gzip压缩的）
                        try:
                            decompressed = gzip.decompress(payload)
                            print(f"   解压后长度: {len(decompressed)}")
                            try:
                                text = decompressed.decode('utf-8')
                                print(f"   解压后文本: {text}")
                                if text.startswith('{'):
                                    json_data = json.loads(text)
                                    print(
                                        f"   解压后JSON: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
                            except:
                                print(f"   解压后二进制: {decompressed[:50]}")
                        except:
                            print(f"   不是gzip数据")

                        # 3. 如果是音频数据（类型0xB）
                        if message_type == 0xb and flags != 0:
                            if len(payload) >= 8:
                                seq_num = struct.unpack('>i', payload[:4])[0]
                                data_size = struct.unpack(
                                    '>I', payload[4:8])[0]
                                audio_data = payload[8:]

                                print(f"   音频序列号: {seq_num}")
                                print(f"   音频数据大小: {data_size}")
                                print(f"   实际音频数据: {len(audio_data)} bytes")

                                if len(audio_data) > 0:
                                    audio_array = np.frombuffer(
                                        audio_data, dtype=np.int16)
                                    print(f"   音频数组形状: {audio_array.shape}")
                                    print(
                                        f"   音频范围: [{np.min(audio_array)}, {np.max(audio_array)}]")
                                    print(
                                        f"   音频平均值: {np.mean(audio_array):.2f}")
                                    print(
                                        f"   是否全零: {np.all(audio_array == 0)}")

                                    if seq_num < 0:
                                        print("   → 传输结束")
                                    else:
                                        print("   → 传输中...")

            return len(responses) > 0

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_doubao_account_status():
    """检查Doubao账户状态"""
    print(f"\n=== 检查账户状态建议 ===")
    print("1. 登录火山引擎控制台: https://www.volcengine.com")
    print("2. 进入语音合成服务")
    print("3. 检查:")
    print("   - 账户余额")
    print("   - 服务开通状态")
    print("   - API配额")
    print("   - AppID和Token的有效性")

    print(f"\n4. 可能的Voice ID格式:")
    print("   - zh_female_xiaohe_uranus_bigtts")
    print("   - zh_female_xiaoyu_uranus_bigtts")
    print("   - zh_male_xiaoyu_uranus_bigtts")
    print("   - zh_female_xiaoxiao_uranus_bigtts")

    print(f"\n5. 当前配置:")
    print(f"   AppID: {DOUBAO_APPID}")
    print(
        f"   Token: {DOUBAO_TOKEN[:20]}..." if DOUBAO_TOKEN else "   Token: 未配置")
    print(f"   Voice ID: {DOUBAO_VOICE_ID}")


if __name__ == "__main__":
    print("Doubao TTS 详细诊断工具")
    print("=" * 60)

    if not all([DOUBAO_APPID, DOUBAO_TOKEN, DOUBAO_VOICE_ID]):
        print("❌ 缺少必要的环境变量")
        exit(1)

    result = asyncio.run(decode_error_message())

    check_doubao_account_status()

    if result:
        print("\n" + "=" * 60)
        print("💡 诊断完成")
    else:
        print("\n" + "=" * 60)
        print("❌ 无法连接到Doubao服务")
