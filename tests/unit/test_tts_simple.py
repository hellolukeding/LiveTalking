#!/usr/bin/env python3
"""
简化的TTS测试 - 只测试音频生成
"""

import os
import sys
import time

import numpy as np
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def test_doubao_tts_basic():
    """测试豆包TTS基本功能"""
    print("=" * 60)
    print("🎵 豆包TTS基本功能测试")
    print("=" * 60)

    try:
        from ttsreal import DoubaoTTS

        # 检查环境变量
        appid = os.getenv("DOUBAO_APPID")
        token = os.getenv("DOUBAO_TOKEN")
        voice_id = os.getenv("DOUBAO_VOICE_ID")

        print(f"📋 配置检查:")
        print(f"   AppID: {appid}")
        print(f"   Token: {token[:10] + '...' if token else 'None'}")
        print(f"   Voice ID: {voice_id}")

        if not all([appid, token, voice_id]):
            print("❌ 缺少必要的环境变量")
            return False

        # 创建模拟的opt对象
        class MockOpt:
            def __init__(self):
                self.tts = 'doubao'
                self.REF_FILE = voice_id
                self.fps = 30
                self.sessionid = 999

        opt = MockOpt()

        # 创建音频收集器
        class AudioCollector:
            def __init__(self):
                self.audio_frames = []
                self.events = []

            def put_audio_frame(self, audio_chunk, datainfo):
                self.audio_frames.append(audio_chunk.copy())
                if datainfo:
                    self.events.append(datainfo)
                print(
                    f"  ✅ 收到音频帧: {len(audio_chunk)} samples, 事件: {datainfo.get('status', 'unknown')}")

        collector = AudioCollector()

        # 创建TTS实例
        print("\n🔧 初始化TTS...")
        try:
            tts = DoubaoTTS(opt, collector)
            print("✅ TTS实例创建成功")
        except Exception as e:
            print(f"❌ TTS初始化失败: {e}")
            return False

        # 测试文本
        test_text = "你好，这是一个简单的TTS测试。"
        print(f"\n📝 测试文本: {test_text}")
        print("🔄 正在生成音频...")

        # 记录开始时间
        start_time = time.time()

        # 调用音频生成
        try:
            tts.txt_to_audio((test_text, {"test_id": 1}))
            print("✅ 音频生成调用完成")
        except Exception as e:
            print(f"⚠️ 音频生成过程中出现异常: {e}")
            # 继续检查是否生成了部分音频

        generation_time = time.time() - start_time
        print(f"⏱️  生成耗时: {generation_time:.2f}秒")

        # 检查结果
        print(f"\n📊 结果分析:")
        print(f"   生成的音频帧数: {len(collector.audio_frames)}")
        print(f"   事件数量: {len(collector.events)}")

        if len(collector.audio_frames) == 0:
            print("❌ 没有生成任何音频帧")
            print("可能的原因:")
            print("   1. WebSocket连接失败")
            print("   2. 豆包API返回错误")
            print("   3. 网络连接问题")
            return False

        # 合并音频数据
        audio_data = np.concatenate([f for f in collector.audio_frames])
        total_duration = len(audio_data) / 16000
        print(f"   总音频长度: {len(audio_data)} samples ({total_duration:.2f}秒)")

        # 检查音频质量
        max_amp = np.max(np.abs(audio_data))
        print(f"   最大振幅: {max_amp:.4f}")

        if max_amp < 0.01:
            print("❌ 音频振幅太小，可能是静音")
            return False

        # 检查事件
        if collector.events:
            print(f"\n📋 事件记录:")
            for i, event in enumerate(collector.events[:5]):  # 只显示前5个
                print(f"   {i+1}. {event}")

        # 保存音频文件
        try:
            import soundfile as sf
            output_file = "test_tts_output.wav"
            sf.write(output_file, audio_data, 16000)
            print(f"\n💾 音频已保存到: {output_file}")
            print(f"   文件大小: {os.path.getsize(output_file)} bytes")
        except Exception as e:
            print(f"⚠️ 保存音频文件失败: {e}")

        print("\n🎉 TTS基本功能测试通过！")
        print("💡 如果在完整系统中没有声音，请检查:")
        print("   - WebRTC音频轨道连接")
        print("   - 浏览器音频权限")
        print("   - 音频设备选择")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_edge_tts_basic():
    """测试Edge TTS基本功能"""
    print("\n" + "=" * 60)
    print("🌐 Edge TTS基本功能测试（免费）")
    print("=" * 60)

    try:
        from ttsreal import EdgeTTS

        class MockOpt:
            def __init__(self):
                self.tts = 'edgetts'
                self.REF_FILE = 'zh-CN-YunxiNeural'
                self.fps = 30
                self.sessionid = 888

        opt = MockOpt()

        class AudioCollector:
            def __init__(self):
                self.audio_frames = []

            def put_audio_frame(self, audio_chunk, datainfo):
                self.audio_frames.append(audio_chunk.copy())
                print(f"  ✅ 收到音频帧: {len(audio_chunk)} samples")

        collector = AudioCollector()
        tts = EdgeTTS(opt, collector)

        test_text = "这是Edge TTS的测试语音，完全免费。"
        print(f"📝 测试文本: {test_text}")
        print("🔄 正在生成音频...")

        start_time = time.time()
        tts.txt_to_audio((test_text, {"test_id": 2}))
        generation_time = time.time() - start_time

        print(f"✅ 生成完成，耗时: {generation_time:.2f}秒")

        if collector.audio_frames:
            audio_data = np.concatenate(collector.audio_frames)
            print(f"🔊 音频长度: {len(audio_data)/16000:.2f}秒")

            # 保存音频
            try:
                import soundfile as sf
                output_file = "test_edge_tts_output.wav"
                sf.write(output_file, audio_data, 16000)
                print(f"💾 Edge TTS音频已保存到: {output_file}")
            except:
                pass

            return True
        else:
            print("❌ 没有生成音频")
            return False

    except Exception as e:
        print(f"❌ Edge TTS测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("TTS基础功能测试")
    print("=" * 60)

    # 检查环境变量
    print("🔍 检查环境变量...")
    required_vars = ["DOUBAO_APPID", "DOUBAO_TOKEN", "DOUBAO_VOICE_ID"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        print(f"❌ 缺少环境变量: {', '.join(missing)}")
        print("请确保以下环境变量已设置:")
        for var in required_vars:
            value = os.getenv(var, "未设置")
            print(f"   {var}: {value}")
        return False

    print("✅ 环境变量检查通过")

    # 运行测试
    results = []

    print("\n🎯 开始测试豆包TTS...")
    result1 = test_doubao_tts_basic()
    results.append(("豆包TTS", result1))

    # 询问是否测试Edge TTS
    response = input("\n是否测试Edge TTS？(y/n): ").strip().lower()
    if response == 'y':
        result2 = test_edge_tts_basic()
        results.append(("Edge TTS", result2))

    # 结果汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(r for _, r in results)

    print("=" * 60)
    if all_passed:
        print("🎉 所有测试通过！TTS系统工作正常！")
        print("\n💡 如果在完整LiveTalking系统中没有声音:")
        print("   1. 检查WebRTC连接是否建立")
        print("   2. 检查浏览器音频权限")
        print("   3. 检查音频设备选择")
        print("   4. 查看浏览器控制台是否有错误")
    else:
        print("⚠️  部分测试失败，请检查TTS配置和网络连接")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
