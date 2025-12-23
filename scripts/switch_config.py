#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置切换工具
帮助用户快速切换到可用的TTS和ASR服务配置
"""

import os
import sys

from dotenv import load_dotenv, set_key, unset_key

# 加载环境变量
load_dotenv()


def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def show_current_config():
    """显示当前配置"""
    print_header("当前配置")

    tts_type = os.getenv('TTS_TYPE', '未设置')
    asr_type = os.getenv('ASR_TYPE', '未设置')

    print(f"TTS 服务: {tts_type}")
    print(f"ASR 服务: {asr_type}")
    print(f"FPS: {os.getenv('FPS', '20')}")
    print()


def configure_edge_tts():
    """配置Edge TTS（推荐）"""
    print_header("配置 Edge TTS")

    print("✅ Edge TTS 是免费的，无需API密钥")
    print("   支持多种中文语音")
    print()

    voices = [
        ("zh-CN-YunxiNeural", "云希 (男声)"),
        ("zh-CN-YunxiaNeural", "云夏 (女声)"),
        ("zh-CN-XiaoxiaoNeural", "晓晓 (女声)"),
        ("zh-CN-XiaoyiNeural", "晓伊 (女声)"),
        ("zh-CN-YunjianNeural", "云健 (男声)"),
    ]

    print("可用语音:")
    for i, (voice, desc) in enumerate(voices, 1):
        print(f"  {i}. {voice} - {desc}")

    choice = input("\n选择语音 (1-5, 默认1): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(voices):
        voice = voices[int(choice)-1][0]
    else:
        voice = voices[0][0]

    # 更新配置
    set_key('.env', 'TTS_TYPE', 'edge')
    set_key('.env', 'EDGE_TTS_VOICE', voice)

    print(f"\n✅ 已配置 Edge TTS")
    print(f"   语音: {voice}")
    print()


def configure_doubao_tts():
    """配置豆包TTS"""
    print_header("配置 豆包 TTS")

    print("⚠️  需要有效的火山引擎API Token")
    print("   请确保已获取以下信息:")
    print("   - AppID")
    print("   - Token")
    print("   - Voice ID")
    print()

    appid = input("AppID: ").strip()
    token = input("Token: ").strip()
    voice_id = input("Voice ID (默认: zh_female_xiaohe_uranus_bigtts): ").strip()

    if not voice_id:
        voice_id = "zh_female_xiaohe_uranus_bigtts"

    if appid and token:
        set_key('.env', 'TTS_TYPE', 'doubao')
        set_key('.env', 'DOUBAO_APPID', appid)
        set_key('.env', 'DOUBAO_TOKEN', token)
        set_key('.env', 'DOUBAO_VOICE_ID', voice_id)

        print(f"\n✅ 已配置豆包 TTS")
        print(f"   AppID: {appid}")
        print(f"   Voice ID: {voice_id}")
    else:
        print("\n❌ 配置失败，缺少必要信息")

    print()


def configure_tencent_tts():
    """配置腾讯TTS"""
    print_header("配置 腾讯 TTS")

    print("⚠️  需要有效的腾讯云API密钥")
    print("   请确保已获取以下信息:")
    print("   - AppID")
    print("   - Secret ID")
    print("   - Secret Key")
    print()

    appid = input("AppID: ").strip()
    secret_id = input("Secret ID: ").strip()
    secret_key = input("Secret Key: ").strip()
    voice_type = input("Voice Type (默认: 1001): ").strip() or "1001"

    if appid and secret_id and secret_key:
        set_key('.env', 'TTS_TYPE', 'tencent')
        set_key('.env', 'TENCENT_APPID', appid)
        set_key('.env', 'TENCENT_SECRET_ID', secret_id)
        set_key('.env', 'TENCENT_SECRET_KEY', secret_key)
        set_key('.env', 'TENCENT_VOICE_TYPE', voice_type)

        print(f"\n✅ 已配置腾讯 TTS")
        print(f"   AppID: {appid}")
        print(f"   Voice Type: {voice_type}")
    else:
        print("\n❌ 配置失败，缺少必要信息")

    print()


def configure_asr():
    """配置ASR服务"""
    print_header("配置 ASR 服务")

    print("可用的ASR服务:")
    print("  1. Lip ASR (本地，推荐)")
    print("  2. 腾讯 ASR (需要API密钥)")
    print("  3. FunASR (需要安装)")
    print("  4. Huber ASR (需要安装)")
    print()

    choice = input("选择ASR服务 (1-4, 默认1): ").strip()

    if choice == '2':
        print("\n配置腾讯 ASR:")
        print("需要以下信息:")
        print("   - AppID")
        print("   - Secret ID")
        print("   - Secret Key")
        print()

        appid = input("AppID: ").strip()
        secret_id = input("Secret ID: ").strip()
        secret_key = input("Secret Key: ").strip()

        if appid and secret_id and secret_key:
            set_key('.env', 'ASR_TYPE', 'tencent')
            set_key('.env', 'TENCENT_APPID', appid)
            set_key('.env', 'TENCENT_ASR_SECRET_ID', secret_id)
            set_key('.env', 'TENCENT_ASR_SECRET_KEY', secret_key)
            print("\n✅ 已配置腾讯 ASR")
        else:
            print("\n❌ 配置失败")

    elif choice == '3':
        set_key('.env', 'ASR_TYPE', 'funasr')
        print("\n✅ 已配置 FunASR")
        print("   请确保已安装: pip install funasr")

    elif choice == '4':
        set_key('.env', 'ASR_TYPE', 'huber')
        print("\n✅ 已配置 Huber ASR")
        print("   请确保已安装相关依赖")

    else:
        set_key('.env', 'ASR_TYPE', 'lip')
        print("\n✅ 已配置 Lip ASR")
        print("   使用本地ASR服务")

    print()


def configure_other_settings():
    """配置其他设置"""
    print_header("配置其他设置")

    fps = input("音频FPS (默认30): ").strip() or "30"
    max_session = input("最大会话数 (默认1): ").strip() or "1"
    listen_port = input("监听端口 (默认8010): ").strip() or "8010"

    set_key('.env', 'FPS', fps)
    set_key('.env', 'MAX_SESSION', max_session)
    set_key('.env', 'LISTEN_PORT', listen_port)

    print(f"\n✅ 已更新其他设置")
    print(f"   FPS: {fps}")
    print(f"   最大会话: {max_session}")
    print(f"   端口: {listen_port}")
    print()


def test_configuration():
    """测试配置"""
    print_header("测试配置")

    # 检查TTS配置
    tts_type = os.getenv('TTS_TYPE')
    print(f"TTS 服务: {tts_type}")

    if tts_type == 'edge':
        try:
            import edge_tts
            print("✅ Edge TTS: 已安装")
        except ImportError:
            print("❌ Edge TTS: 未安装 (pip install edge-tts)")

    elif tts_type == 'doubao':
        appid = os.getenv('DOUBAO_APPID')
        token = os.getenv('DOUBAO_TOKEN')
        if appid and token:
            print("✅ 豆包 TTS: 配置完整")
        else:
            print("❌ 豆包 TTS: 配置不完整")

    elif tts_type == 'tencent':
        appid = os.getenv('TENCENT_APPID')
        secret_key = os.getenv('TENCENT_SECRET_KEY')
        if appid and secret_key:
            print("✅ 腾讯 TTS: 配置完整")
        else:
            print("❌ 腾讯 TTS: 配置不完整")

    # 检查ASR配置
    asr_type = os.getenv('ASR_TYPE')
    print(f"\nASR 服务: {asr_type}")

    if asr_type == 'lip':
        try:
            from lipasr import LipASR
            print("✅ Lip ASR: 可用")
        except ImportError:
            print("❌ Lip ASR: 不可用")

    elif asr_type == 'tencent':
        appid = os.getenv('TENCENT_APPID')
        secret_key = os.getenv('TENCENT_ASR_SECRET_KEY')
        if appid and secret_key:
            print("✅ 腾讯 ASR: 配置完整")
        else:
            print("❌ 腾讯 ASR: 配置不完整")

    elif asr_type == 'funasr':
        try:
            import funasr
            print("✅ FunASR: 已安装")
        except ImportError:
            print("❌ FunASR: 未安装")

    print()


def main():
    """主函数"""
    while True:
        clear_screen()
        print_header("LiveTalking 配置工具")

        show_current_config()

        print("可选操作:")
        print("  1. 配置 Edge TTS (推荐，免费)")
        print("  2. 配置 豆包 TTS")
        print("  3. 配置 腾讯 TTS")
        print("  4. 配置 ASR 服务")
        print("  5. 配置其他设置")
        print("  6. 测试当前配置")
        print("  7. 查看推荐配置")
        print("  0. 退出")
        print()

        choice = input("请选择操作 (0-7): ").strip()

        if choice == '1':
            configure_edge_tts()
        elif choice == '2':
            configure_doubao_tts()
        elif choice == '3':
            configure_tencent_tts()
        elif choice == '4':
            configure_asr()
        elif choice == '5':
            configure_other_settings()
        elif choice == '6':
            test_configuration()
        elif choice == '7':
            print_header("推荐配置")
            print("🎯 最简单可用的配置:")
            print()
            print("1. 安装 Edge TTS:")
            print("   pip install edge-tts")
            print()
            print("2. 运行配置工具:")
            print("   python switch_config.py")
            print("   选择 1 (配置 Edge TTS)")
            print("   选择 4 (配置 ASR) -> 选择 1 (Lip ASR)")
            print()
            print("3. 启动项目:")
            print("   python start_quick.py")
            print()
            input("按回车继续...")

        elif choice == '0':
            print("\n👋 再见!")
            break
        else:
            print("\n❌ 无效选择")
            input("按回车继续...")


if __name__ == "__main__":
    main()
