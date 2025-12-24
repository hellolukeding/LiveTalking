#!/usr/bin/env python3
"""简单音频调试脚本"""

import base64
import os

import numpy as np
import requests


def debug_doubao_tts():
    """调试豆包TTS音频格式"""

    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv(
        "DOUBAO_VOICE_ID") or "zh_female_shuangkuaisisi_moon_bigtts"

    if not appid or not token:
        print("❌ 缺少环境变量")
        return

    # 发送测试请求
    request_json = {
        "app": {"appid": appid, "token": token, "cluster": "volcano_tts"},
        "user": {"uid": "test-user"},
        "audio": {
            "voice_type": voice_id,
            "encoding": "wav",
            "rate": 16000,
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": "test-req",
            "text": "测试音频",
            "text_type": "plain",
            "operation": "query"
        }
    }

    print("🔍 发送TTS请求...")
    try:
        response = requests.post(
            "https://openspeech.bytedance.com/api/v1/tts",
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code != 200:
            print(f"❌ HTTP错误: {response.status_code}")
            return

        result = response.json()

        if result.get("code", 0) != 3000:
            print(f"❌ API错误: {result.get('code')}, {result.get('message')}")
            return

        # 获取音频数据
        audio_base64 = None
        if "data" in result and isinstance(result["data"], dict):
            audio_base64 = result["data"].get("audio")

        if not audio_base64:
            print("❌ 没有音频数据")
            return

        # 解码
        audio_bytes = base64.b64decode(audio_base64)
        print(f"✅ 收到音频: {len(audio_bytes)} bytes")

        # 分析音频格式
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_array.astype(np.float32) / 32767.0

        print(f"\n📊 音频分析:")
        print(
            f"   16-bit数组: {audio_array.shape}, 范围: [{audio_array.min()}, {audio_array.max()}]")
        print(
            f"   32-bit数组: {audio_float.shape}, 范围: [{audio_float.min():.4f}, {audio_float.max():.4f}]")

        # 检查异常值
        if np.any(np.isnan(audio_float)) or np.any(np.isinf(audio_float)):
            print("   ❌ 包含NaN或Inf值")

        silent_ratio = np.sum(np.abs(audio_float) < 0.01) / len(audio_float)
        print(f"   静音比例: {silent_ratio:.2%}")

        duration_ms = len(audio_float) / 16000 * 1000
        print(f"   音频时长: {duration_ms:.1f}ms")

        # 检查320样本块
        chunk_size = 320
        if len(audio_float) >= chunk_size:
            first_chunk = audio_float[:chunk_size]
            print(
                f"   第一个320样本块: [{first_chunk.min():.4f}, {first_chunk.max():.4f}]")
            print(
                f"   静音比例: {np.sum(np.abs(first_chunk) < 0.01) / chunk_size:.2%}")

        # 测试格式转换
        print(f"\n🔄 格式转换测试:")
        test_frame = (audio_float[:320] * 32767).astype(np.int16)
        print(
            f"   转换后: {test_frame.dtype}, 范围: [{test_frame.min()}, {test_frame.max()}]")

        # 检查是否需要重采样
        if duration_ms > 1000:
            print(f"   ⚠️ 音频过长，可能需要分块处理")

        return audio_float

    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("LiveTalking 音频调试工具")
    print("="*50)
    debug_doubao_tts()
    print("="*50)
