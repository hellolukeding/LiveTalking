#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试start_quick.py的修复是否正确
"""

import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))


def test_imports():
    """测试所有必要的导入"""
    print("🔍 测试导入...")

    try:
        import json
        print("✅ json 导入成功")
    except ImportError as e:
        print(f"❌ json 导入失败: {e}")
        return False

    try:
        from logger import logger
        print("✅ logger 导入成功")
    except ImportError as e:
        print(f"❌ logger 导入失败: {e}")
        return False

    try:
        import torch
        print("✅ torch 导入成功")
    except ImportError as e:
        print(f"❌ torch 导入失败: {e}")
        return False

    try:
        from dotenv import load_dotenv
        print("✅ dotenv 导入成功")
    except ImportError as e:
        print(f"❌ dotenv 导入失败: {e}")
        return False

    return True


def test_config_setup():
    """测试配置设置"""
    print("\n🔍 测试配置设置...")

    try:
        from start_quick import setup_config
        config = setup_config()

        print(f"✅ 配置创建成功")
        print(f"   TTS: {config.tts}")
        print(f"   ASR: {config.asr}")
        print(f"   REF_FILE: {config.REF_FILE}")
        print(f"   模型: {config.model}")
        print(f"   端口: {config.listenport}")

        return True
    except Exception as e:
        print(f"❌ 配置设置失败: {e}")
        return False


def test_doubao_tts():
    """测试豆包TTS类"""
    print("\n🔍 测试豆包TTS...")

    try:
        from ttsreal import DoubaoTTS
        print("✅ DoubaoTTS 类导入成功")

        # 检查类是否存在txt_to_audio方法
        if hasattr(DoubaoTTS, 'txt_to_audio'):
            print("✅ DoubaoTTS.txt_to_audio 方法存在")
        else:
            print("❌ DoubaoTTS.txt_to_audio 方法不存在")
            return False

        return True
    except Exception as e:
        print(f"❌ DoubaoTTS 测试失败: {e}")
        return False


def main():
    print("=" * 60)
    print("🚀 LiveTalking 修复验证测试")
    print("=" * 60)

    all_passed = True

    # 测试导入
    if not test_imports():
        all_passed = False

    # 测试配置
    if not test_config_setup():
        all_passed = False

    # 测试TTS
    if not test_doubao_tts():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有测试通过！修复成功。")
        print("\n现在可以运行: python start_quick.py")
    else:
        print("❌ 部分测试失败，请检查上述错误。")
    print("=" * 60)


if __name__ == "__main__":
    main()
