#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试腾讯ASR和豆包TTS配置
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


def test_tencent_asr():
    """测试腾讯ASR配置"""
    print("=" * 60)
    print("🔍 测试腾讯ASR配置")
    print("=" * 60)

    appid = os.getenv('TENCENT_APPID')
    secret_id = os.getenv('TENCENT_ASR_SECRET_ID')
    secret_key = os.getenv('TENCENT_ASR_SECRET_KEY')

    print(f"AppID: {appid}")
    print(f"SecretID: {secret_id}")
    print(f"SecretKey: {secret_key}")

    if not all([appid, secret_id, secret_key]):
        print("❌ 腾讯ASR配置不完整")
        if not appid:
            print("  - 缺少 TENCENT_APPID")
        if not secret_id:
            print("  - 缺少 TENCENT_ASR_SECRET_ID")
        if not secret_key:
            print("  - 缺少 TENCENT_ASR_SECRET_KEY")
        return False

    print("✅ 腾讯ASR配置完整")

    # 检查是否在app.py中使用
    try:
        from tencentasr import TencentASR
        print("✅ tencentasr模块存在")
        return True
    except ImportError as e:
        print(f"❌ tencentasr模块导入失败: {e}")
        return False


def test_doubao_tts():
    """测试豆包TTS配置"""
    print("\n" + "=" * 60)
    print("🔍 测试豆包TTS配置")
    print("=" * 60)

    appid = os.getenv('DOUBAO_APPID')
    token = os.getenv('DOUBAO_TOKEN')
    voice_id = os.getenv('DOUBAO_VOICE_ID')

    print(f"AppID: {appid}")
    print(f"Token: {token[:10] if token else 'None'}...")
    print(f"VoiceID: {voice_id}")

    if not all([appid, token, voice_id]):
        print("❌ 豆包TTS配置不完整")
        if not appid:
            print("  - 缺少 DOUBAO_APPID")
        if not token:
            print("  - 缺少 DOUBAO_TOKEN")
        if not voice_id:
            print("  - 缺少 DOUBAO_VOICE_ID")
        return False

    print("✅ 豆包TTS配置完整")

    # 测试API连接
    print("\n📡 测试豆包TTS API连接...")
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
            "text": "测试",
            "text_type": "plain",
            "operation": "submit"
        }
    }

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=10)
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ 豆包TTS API连接成功")
            return True
        elif response.status_code == 401:
            print("❌ 认证失败，Token无效")
            print(f"错误信息: {response.text}")
            return False
        else:
            print(f"⚠️  API返回异常: {response.status_code}")
            print(f"响应: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 网络连接失败: {e}")
        return False


def check_app_usage():
    """检查app.py使用情况"""
    print("\n" + "=" * 60)
    print("🔍 检查app.py配置")
    print("=" * 60)

    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查TTS配置
        if 'tts = "doubao"' in content or 'tts = "tencent"' in content:
            print("✅ app.py中TTS配置正确")
        else:
            print("⚠️  app.py中TTS配置可能需要检查")

        # 检查ASR配置
        if 'asr = "tencent"' in content or 'asr = "lip"' in content:
            print("✅ app.py中ASR配置正确")
        else:
            print("⚠️  app.py中ASR配置可能需要检查")

    except Exception as e:
        print(f"❌ 读取app.py失败: {e}")


def main():
    """主函数"""
    print("🚀 LiveTalking 服务配置测试")
    print()

    tencent_ok = test_tencent_asr()
    doubao_ok = test_doubao_tts()
    check_app_usage()

    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    if tencent_ok and doubao_ok:
        print("✅ 所有服务配置正确")
        print("\n🎉 可以启动项目:")
        print("   python app.py")
    else:
        print("❌ 部分服务配置有问题")
        print("\n🔧 解决方案:")
        if not tencent_ok:
            print("  - 腾讯ASR: 需要填写 TENCENT_APPID")
        if not doubao_ok:
            print("  - 豆包TTS: 需要有效的 Token")
        print("\n💡 建议:")
        print("  - 运行: python switch_config.py")
        print("  - 选择: 1 (配置Edge TTS) + 4 (配置Lip ASR)")
        print("  - 或者获取新的豆包Token和腾讯AppID")


if __name__ == "__main__":
    main()
