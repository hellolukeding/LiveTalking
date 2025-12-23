#!/usr/bin/env python3
"""
解码Doubao错误消息0xF
"""
import asyncio
import gzip
import json
import os
import struct
import uuid
import zlib

import numpy as np
import websockets
from dotenv import load_dotenv

load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv("DOUBAO_VOICE_ID")


def decode_doubao_error(payload):
    """尝试解码Doubao错误消息"""
    print(f"尝试解码错误消息...")
    print(f"Payload hex: {payload.hex()}")

    # 1. 尝试直接解压payload
    try:
        # 移除可能的头部
        if payload.startswith(b'\x02\xae\xa5'):
            # 找到gzip头部
            gzip_start = payload.find(b'\x1f\x8b')
            if gzip_start > 0:
                compressed_data = payload[gzip_start:]
                decompressed = zlib.decompress(
                    compressed_data, 16+zlib.MAX_WBITS)
                print(f"✅ 解压成功 (跳过头部): {decompressed}")
                try:
                    json_data = json.loads(decompressed.decode('utf-8'))
                    print(
                        f"JSON错误信息: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
                    return json_data
                except:
                    print(f"文本: {decompressed.decode('utf-8')}")
                    return decompressed
    except Exception as e:
        print(f"解压失败: {e}")

    # 2. 尝试整个payload作为gzip
    try:
        decompressed = gzip.decompress(payload)
        print(f"✅ 直接解压成功: {decompressed}")
        try:
            json_data = json.loads(decompressed.decode('utf-8'))
            print(
                f"JSON错误信息: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
            return json_data
        except:
            return decompressed
    except:
        pass

    # 3. 尝试查找JSON
    try:
        text = payload.decode('utf-8', errors='ignore')
        if '{' in text:
            start = text.find('{')
            end = text.rfind('}') + 1
            json_str = text[start:end]
            json_data = json.loads(json_str)
            print(
                f"✅ 找到JSON: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
            return json_data
    except:
        pass

    # 4. 尝试不同的编码
    try:
        text = payload.decode('gbk', errors='ignore')
        print(f"GBK解码: {text}")
    except:
        pass

    return None


async def test_different_requests():
    """测试不同的请求参数"""
    print(f"\n=== 测试不同参数 ===")

    _host = "openspeech.bytedance.com"
    api_url = f"wss://{_host}/api/v1/tts/ws_binary"

    # 测试用例
    test_cases = [
        {
            "name": "原始配置",
            "voice_type": DOUBAO_VOICE_ID,
            "text": "你好，测试"
        },
        {
            "name": "简单文本",
            "voice_type": DOUBAO_VOICE_ID,
            "text": "123"
        },
        {
            "name": "英文文本",
            "voice_type": DOUBAO_VOICE_ID,
            "text": "Hello"
        },
        {
            "name": "不同语音",
            "voice_type": "zh_female_xiaoyu_uranus_bigtts",
            "text": "你好"
        },
        {
            "name": "带标点",
            "voice_type": DOUBAO_VOICE_ID,
            "text": "你好！"
        }
    ]

    for test in test_cases:
        print(f"\n🧪 测试: {test['name']}")
        print(f"   Voice: {test['voice_type']}")
        print(f"   Text: {test['text']}")

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
                "voice_type": test['voice_type'],
                "encoding": "pcm",
                "rate": 16000,
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": test['text'],
                "text_type": "plain",
                "operation": "submit"
            }
        }

        # 准备请求
        default_header = bytearray(b'\x11\x10\x11\x00')
        payload_bytes = str.encode(json.dumps(request_json))
        payload_bytes = gzip.compress(payload_bytes)
        full_client_request = bytearray(default_header)
        full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
        full_client_request.extend(payload_bytes)

        header = {"Authorization": f"Bearer {DOUBAO_TOKEN}"}

        try:
            async with websockets.connect(api_url, extra_headers=header, ping_interval=None, close_timeout=10) as ws:
                await ws.send(full_client_request)

                # 等待响应
                try:
                    res = await asyncio.wait_for(ws.recv(), timeout=5.0)

                    # 解析响应
                    if len(res) >= 4:
                        header_size = res[0] & 0x0f
                        message_type = res[1] >> 4
                        flags = res[1] & 0x0f
                        payload = res[header_size*4:]

                        print(f"   响应类型: 0x{message_type:X}, 标志: {flags}")

                        if message_type == 0xF:
                            print(f"   ❌ 错误响应")
                            error_info = decode_doubao_error(payload)
                            if error_info:
                                if isinstance(error_info, dict):
                                    if 'error' in error_info or 'message' in error_info:
                                        print(f"   💡 可能原因: {error_info}")
                        elif message_type == 0xB:
                            print(f"   ✅ 音频响应")
                            if flags != 0 and len(payload) >= 8:
                                seq_num = struct.unpack('>i', payload[:4])[0]
                                audio_data = payload[8:]
                                if len(audio_data) > 0:
                                    audio_array = np.frombuffer(
                                        audio_data, dtype=np.int16)
                                    if not np.all(audio_array == 0):
                                        print(f"   🎉 有效音频数据！")
                                        return True
                except asyncio.TimeoutError:
                    print(f"   ⏰ 超时")
        except Exception as e:
            print(f"   ❌ 连接错误: {e}")

    return False


async def test_with_correct_format():
    """使用正确的格式测试"""
    print(f"\n=== 测试标准格式 ===")

    # 参考Doubao官方文档的格式
    _host = "openspeech.bytedance.com"
    api_url = f"wss://{_host}/api/v1/tts/ws_binary"

    # 标准请求格式
    request_json = {
        "app": {
            "appid": DOUBAO_APPID,
            "token": DOUBAO_TOKEN,  # 直接使用token，不是"access_token"
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test_user_123"
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
            "text": "你好，世界",
            "text_type": "plain",
            "operation": "submit"
        }
    }

    print(f"请求体: {json.dumps(request_json, indent=2, ensure_ascii=False)}")

    # 准备请求
    default_header = bytearray(b'\x11\x10\x11\x00')
    payload_bytes = str.encode(json.dumps(request_json))
    payload_bytes = gzip.compress(payload_bytes)
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
    full_client_request.extend(payload_bytes)

    header = {"Authorization": f"Bearer {DOUBAO_TOKEN}"}

    try:
        async with websockets.connect(api_url, extra_headers=header, ping_interval=None, close_timeout=10) as ws:
            print("✅ 连接成功")
            await ws.send(full_client_request)
            print("✅ 请求已发送")

            # 接收所有响应
            responses = []
            while True:
                try:
                    res = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    responses.append(res)
                except asyncio.TimeoutError:
                    break

            print(f"收到 {len(responses)} 个响应")

            for i, res in enumerate(responses):
                print(f"\n响应 {i+1}:")
                if len(res) >= 4:
                    header_size = res[0] & 0x0f
                    message_type = res[1] >> 4
                    flags = res[1] & 0x0f
                    payload = res[header_size*4:]

                    print(
                        f"  类型: 0x{message_type:X}, 标志: {flags}, 载荷: {len(payload)} bytes")

                    if message_type == 0xB and flags != 0:
                        if len(payload) >= 8:
                            seq_num = struct.unpack('>i', payload[:4])[0]
                            audio_data = payload[8:]
                            if len(audio_data) > 0:
                                audio_array = np.frombuffer(
                                    audio_data, dtype=np.int16)
                                print(
                                    f"  🎉 音频数据: {audio_array.shape}, 均值: {np.mean(audio_array):.2f}")
                                if not np.all(audio_array == 0):
                                    print(f"  ✅ 有效音频！")
                                    return True
                    elif message_type == 0xF:
                        print(f"  ❌ 错误消息")
                        error_text = payload.decode('utf-8', errors='ignore')
                        print(f"  错误内容: {error_text}")

            return len(responses) > 0 and any(res[1] >> 4 == 0xB for res in responses)

    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

if __name__ == "__main__":
    print("Doubao TTS 最终诊断工具")
    print("=" * 60)

    if not all([DOUBAO_APPID, DOUBAO_TOKEN, DOUBAO_VOICE_ID]):
        print("❌ 缺少必要的环境变量")
        exit(1)

    print(f"配置:")
    print(f"  AppID: {DOUBAO_APPID}")
    print(f"  Token: {DOUBAO_TOKEN[:30]}...")
    print(f"  Voice ID: {DOUBAO_VOICE_ID}")

    # 1. 测试不同参数
    result1 = asyncio.run(test_different_requests())

    # 2. 测试标准格式
    result2 = asyncio.run(test_with_correct_format())

    print("\n" + "=" * 60)
    if result1 or result2:
        print("🎉 找到有效配置！")
    else:
        print("❌ 所有测试失败")
        print("\n建议:")
        print("1. 检查火山引擎控制台")
        print("2. 确认服务已开通")
        print("3. 检查账户余额")
        print("4. 重新获取Token")
        print("5. 尝试其他语音类型")
