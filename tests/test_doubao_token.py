#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试豆包TTS Token是否有效
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


def test_doubao_token():
    """测试豆包TTS Token"""
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID")

    print("=" * 60)
    print("🔍 测试豆包TTS Token")
    print("=" * 60)

    if not all([appid, token, voice_id]):
        print("❌ 缺少配置参数")
        print(f"  AppID: {appid}")
        print(f"  Token: {token}")
        print(f"  VoiceID: {voice_id}")
        return False

    print(f"✅ 配置参数完整")
    print(f"  AppID: {appid}")
    print(f"  Token: {token[:10]}...")  # 只显示前10个字符
    print(f"  VoiceID: {voice_id}")

    # 测试API连接
    url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "app": {
            "appid": appid,
            "token": "access_token",
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test_user"
        },
        "audio": {
            "voice_type": voice_id,
            "encoding": "pcm",
            "rate": 16000
        },
        "request": {
            "reqid": str(int(time.time())),
            "text": "测试语音",
            "text_type": "plain",
            "operation": "submit"
        }
    }

    print(f"\n📡 正在测试API连接: {url}")

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=15)
        print(f"📊 响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ API连接成功！")
            print("🎉 Token有效，豆包TTS服务可用")
            return True
        elif response.status_code == 401:
            print("❌ 认证失败！Token无效或过期")
            print(f"错误信息: {response.text}")
            return False
        else:
            print(f"⚠️  API返回异常状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络连接失败: {e}")
        return False


if __name__ == "__main__":
    success = test_doubao_token()
    exit(0 if success else 1)
