#!/usr/bin/env python3
"""
豆包TTS HTTP方式测试脚本 - 修复版本
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv


def test_doubao_tts_http():
    """测试豆包TTS的HTTP接口"""

    # 加载环境变量
    load_dotenv()

    # 获取配置
    appid = os.getenv('DOUBAO_APPID')
    token = os.getenv('DOUBAO_TOKEN')
    voice_id = os.getenv('DOUBAO_VOICE_ID', 'zh_female_xiaohe_uranus_bigtts')

    if not appid or not token:
        print("❌ 请在.env文件中配置 DOUBAO_APPID 和 DOUBAO_TOKEN")
        return False

    print("=" * 60)
    print("豆包TTS HTTP方式测试")
    print("=" * 60)
    print(f"AppID: {appid}")
    print(f"Token: {token[:20]}...")
    print(f"VoiceID: {voice_id}")
    print()

    # 构建请求体
    request_json = {
        "app": {
            "appid": appid,
            "token": token,
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test_user"
        },
        "audio": {
            "voice_type": voice_id,
            "encoding": "wav",
            "rate": 16000,
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0
        },
        "request": {
            "reqid": "req-001",
            "text": "你好，世界！",
            "text_type": "plain",
            "operation": "query"
        }
    }

    print("📋 请求体:")
    print(json.dumps(request_json, ensure_ascii=False, indent=2))
    print()

    # 发送请求
    api_url = "https://openspeech.bytedance.com/api/v1/tts"

    try:
        print("🔄 发送HTTP POST请求...")
        response = requests.post(api_url, json=request_json, timeout=30)

        print(f"📊 响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ HTTP请求成功！")

            # 尝试解析JSON
            try:
                data = response.json()
                print("📋 响应数据 (JSON):")
                print(json.dumps(data, ensure_ascii=False, indent=2))

                # 检查响应内容
                if data.get('code') == 3000:
                    print("✅ TTS请求成功！")
                    if 'data' in data:
                        audio_data = data['data']
                        if isinstance(audio_data, str):
                            print(f"✅ 收到音频数据，长度: {len(audio_data)} 字符")
                            print(f"📋 音频数据类型: {type(audio_data)}")

                            # 尝试解码音频数据
                            import base64
                            try:
                                audio_bytes = base64.b64decode(audio_data)
                                print(
                                    f"✅ Base64解码成功，音频字节长度: {len(audio_bytes)}")

                                # 保存音频文件
                                with open('test_doubao_output.wav', 'wb') as f:
                                    f.write(audio_bytes)
                                print("✅ 音频已保存到 test_doubao_output.wav")

                                # 显示音频信息
                                print(f"📊 音频文件大小: {len(audio_bytes)} 字节")
                                return True
                            except Exception as e:
                                print(f"❌ Base64解码失败: {e}")
                                return False
                        else:
                            print(f"❌ 音频数据格式错误: {type(audio_data)}")
                            return False
                    else:
                        print("❌ 响应中没有data字段")
                        return False
                else:
                    print(
                        f"❌ TTS请求失败，错误码: {data.get('code')}, 消息: {data.get('message')}")
                    return False

            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:500]}")
                return False

        else:
            print(f"❌ HTTP请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误，请检查网络")
        return False
    except Exception as e:
        print(f"❌ 发生异常: {e}")
        return False


if __name__ == "__main__":
    success = test_doubao_tts_http()
    sys.exit(0 if success else 1)
