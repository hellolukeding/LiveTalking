#!/usr/bin/env python3
"""
测试修复后的配置：TTS和嘴形驱动验证
"""

import os
import sys

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def test_config():
    """测试配置是否正确"""
    print("=" * 60)
    print("🔧 配置验证测试")
    print("=" * 60)

    # 检查环境变量
    tts_type = os.getenv('TTS_TYPE', 'edge')
    asr_type = os.getenv('ASR_TYPE', 'lip')

    print(f"✅ TTS类型: {tts_type}")
    print(f"✅ ASR类型: {asr_type}")

    # 检查豆包TTS配置
    if tts_type == 'doubao':
        appid = os.getenv('DOUBAO_APPID')
        token = os.getenv('DOUBAO_TOKEN')
        voice_id = os.getenv('DOUBAO_VOICE_ID')

        if appid and token and voice_id:
            print(f"✅ 豆包TTS配置完整")
            print(f"   - AppID: {appid}")
            print(f"   - Voice ID: {voice_id}")
        else:
            print("❌ 豆包TTS配置缺失")
            return False

    # 检查腾讯ASR配置
    if asr_type == 'tencent':
        secret_id = os.getenv('TENCENT_ASR_SECRET_ID')
        secret_key = os.getenv('TENCENT_ASR_SECRET_KEY')

        if secret_id and secret_key:
            print(f"✅ 腾讯ASR配置完整")
            print(f"   - Secret ID: {secret_id[:10]}...")
        else:
            print("❌ 腾讯ASR配置缺失")
            return False

    return True


def test_imports():
    """测试关键模块导入"""
    print("\n" + "=" * 60)
    print("📦 模块导入测试")
    print("=" * 60)

    try:
        from ttsreal import DoubaoTTS, EdgeTTS, State
        print("✅ TTS模块导入成功")

        from lipreal import LipReal, load_avatar, load_model
        print("✅ LipReal模块导入成功")

        from basereal import BaseReal
        print("✅ BaseReal模块导入成功")

        from lipasr import LipASR
        print("✅ LipASR模块导入成功")

        return True

    except Exception as e:
        print(f"❌ 模块导入失败: {e}")
        return False


def test_doubao_connection():
    """测试豆包TTS连接"""
    print("\n" + "=" * 60)
    print("🌐 豆包TTS连接测试")
    print("=" * 60)

    try:
        from ttsreal import DoubaoTTS, DoubaoWebSocketConnection

        appid = os.getenv('DOUBAO_APPID')
        token = os.getenv('DOUBAO_TOKEN')
        voice_id = os.getenv('DOUBAO_VOICE_ID')

        if not all([appid, token, voice_id]):
            print("❌ 缺少配置")
            return False

        print("正在测试WebSocket连接...")
        conn = DoubaoWebSocketConnection(appid, token, voice_id)

        if conn.connect():
            print("✅ WebSocket连接成功")
            conn.close()
            return True
        else:
            print("❌ WebSocket连接失败")
            return False

    except Exception as e:
        print(f"❌ 连接测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("LiveTalking 修复验证测试")
    print("=" * 60)

    tests = [
        ("配置验证", test_config),
        ("模块导入", test_imports),
        ("豆包TTS连接", test_doubao_connection),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} 测试异常: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
        if not result:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 所有测试通过！系统已修复完成。")
        print("\n现在可以运行: poetry run python start_quick.py")
    else:
        print("⚠️  部分测试失败，请检查配置。")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
