#!/usr/bin/env python3
"""
豆包TTS HTTP方式测试 - 基于您提供的正确格式
===========================================
"""

import base64
import json
import os

import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")
DOUBAO_VOICE_ID = os.getenv(
    "DOUBAO_VOICE_ID") or "zh_female_xiaohe_uranus_bigtts"

print("=" * 60)
print("豆包TTS HTTP方式测试")
print("=" * 60)
print(f"AppID: {DOUBAO_APPID}")
print(f"Token: {DOUBAO_TOKEN[:20]}...")
print(f"VoiceID: {DOUBAO_VOICE_ID}")
print()


def test_doubao_http():
    """测试豆包TTS HTTP接口"""

    # 接口地址
    api_url = "https://openspeech.bytedance.com/api/v1/tts"

    # 测试文本
    test_text = "你好，世界！"

    # 构建请求 - 完全按照您提供的正确格式
    request_json = {
        "app": {
            "appid": DOUBAO_APPID,
            "token": DOUBAO_TOKEN,
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test_user"
        },
        "audio": {
            "voice_type": DOUBAO_VOICE_ID,
            "encoding": "wav",
            "rate": 16000,
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": "req-001",
            "text": test_text,
            "text_type": "plain",
            "operation": "query"
        }
    }

    print("📋 请求体:")
    print(json.dumps(request_json, indent=2, ensure_ascii=False))
    print()

    try:
        print("🔄 发送HTTP POST请求...")
        response = requests.post(
            api_url,
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        print(f"📊 响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ HTTP请求成功！")

            # 尝试解析响应
            try:
                result = response.json()
                print("📋 响应数据 (JSON):")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except:
                print("📋 响应数据 (文本):")
                print(
                    response.text[:500] + "..." if len(response.text) > 500 else response.text)
                result = response.text

            print()

            # 检查响应结构
            if isinstance(result, str):
                # 如果是字符串，尝试解析JSON
                try:
                    result = json.loads(result)
                except:
                    print("❌ 响应不是有效的JSON格式")
                    return False

            code = result.get("code", 0)
            message = result.get("message", "")
            audio_base64 = result.get("data", {}).get("audio")

            if code == 0 and audio_base64:
                print("✅ 音频生成成功！")
                print(f"   Base64长度: {len(audio_base64)} 字符")

                # 解码base64
                audio_bytes = base64.b64decode(audio_base64)
                print(f"   音频数据大小: {len(audio_bytes)} bytes")

                # 保存为文件
                with open("test_output.wav", "wb") as f:
                    f.write(audio_bytes)
                print("   ✅ 已保存为 test_output.wav")

                # 检查音频数据
                import numpy as np
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                print(f"   音频样本数: {len(audio_array)}")
                print(f"   音频均值: {np.mean(audio_array):.2f}")
                print(
                    f"   音频范围: [{np.min(audio_array)}, {np.max(audio_array)}]")

                if np.all(audio_array == 0):
                    print("   ⚠️  警告: 音频数据全为零")
                else:
                    print("   🎉 音频数据有效！")

                return True
            else:
                print(f"❌ API返回错误: code={code}, message={message}")
                return False
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False


if __name__ == "__main__":
    # 检查环境变量
    if not all([DOUBAO_APPID, DOUBAO_TOKEN]):
        print("❌ 缺少必要的环境变量！")
        print("请检查 .env 文件中的 DOUBAO_APPID 和 DOUBAO_TOKEN")
        exit(1)

    success = test_doubao_http()

    print()
    print("=" * 60)
    if success:
        print("🎉 测试通过！豆包TTS HTTP方式工作正常。")
        print()
        print("关键要点总结:")
        print("1. ✅ 使用 HTTPS POST 接口")
        print("2. ✅ Token 在 JSON body 中，不是 Authorization header")
        print("3. ✅ operation='query' 而不是 'submit'")
        print("4. ✅ encoding='wav' 返回base64编码的wav数据")
        print("5. ✅ 需要解码base64得到原始音频")
        print()
        print("LiveTalking 现在应该可以正常工作了！")
    else:
        print("❌ 测试失败")
