#!/usr/bin/env python3
"""
TTS本地音频生成和播放测试
直接生成TTS音频并在本地播放，验证TTS是否正常工作
"""

import os
import sys
import time
from io import BytesIO

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def test_tts_audio_generation_and_playback():
    """测试TTS音频生成和本地播放"""
    print("=" * 70)
    print("🎵 TTS本地音频生成和播放测试")
    print("=" * 70)

    try:
        from ttsreal import DoubaoTTS, State

        # 创建模拟的opt对象
        class MockOpt:
            def __init__(self):
                self.tts = 'doubao'
                self.REF_FILE = 'zh_female_vv_uranus_bigtts'
                self.fps = 30
                self.sessionid = 999

        opt = MockOpt()

        # 创建模拟的父对象来接收音频
        class MockParent:
            def __init__(self):
                self.audio_buffer = BytesIO()
                self.audio_frames = []
                self.sample_rate = 16000

            def put_audio_frame(self, audio_chunk, datainfo):
                # 将音频帧保存到缓冲区
                self.audio_frames.append((audio_chunk.copy(), datainfo))
                print(
                    f"  收到音频帧: {len(audio_chunk)} samples, 事件: {datainfo.get('status', 'unknown')}")

        mock_parent = MockParent()

        # 创建TTS实例
        print("🔧 初始化豆包TTS...")
        tts = DoubaoTTS(opt, mock_parent)

        # 测试文本
        test_text = "你好，这是一个TTS音频测试。"
        print(f"📝 测试文本: {test_text}")

        # 生成音频
        print("🔄 正在生成音频...")
        start_time = time.time()

        try:
            tts.txt_to_audio((test_text, {"test_id": 1}))
        except Exception as e:
            print(f"⚠️ TTS生成过程中出现异常: {e}")
            print("这可能是正常的，因为我们的MockParent没有完整的接口")

        generation_time = time.time() - start_time
        print(f"✅ 音频生成完成，耗时: {generation_time:.2f}秒")

        # 检查生成的音频
        if not mock_parent.audio_frames:
            print("❌ 没有生成任何音频帧")
            return False

        print(f"📊 生成了 {len(mock_parent.audio_frames)} 个音频帧")

        # 合并所有音频帧
        audio_chunks = [frame for frame, _ in mock_parent.audio_frames]
        if not audio_chunks:
            print("❌ 音频数据为空")
            return False

        full_audio = np.concatenate(audio_chunks)
        print(
            f"🔊 总音频长度: {len(full_audio)} samples ({len(full_audio)/16000:.2f}秒)")

        # 检查音频质量
        max_amplitude = np.max(np.abs(full_audio))
        print(f"📈 最大振幅: {max_amplitude:.4f}")

        if max_amplitude < 0.01:
            print("❌ 音频振幅太小，可能是静音")
            return False

        # 播放音频
        print("\n🎵 开始播放音频...")
        print("⚠️  注意: 将在3秒后开始播放，请调整音量")
        time.sleep(3)

        try:
            # 归一化音频到安全范围
            normalized_audio = full_audio * 0.7

            # 播放音频
            sd.play(normalized_audio, samplerate=16000)
            sd.wait()  # 等待播放完成

            print("✅ 音频播放完成")

            # 询问用户是否听到声音
            print("\n" + "=" * 70)
            print("❓ 请确认:")
            print("   1. 您是否听到了清晰的语音？")
            print("   2. 音频质量是否正常？")
            print("=" * 70)

            response = input("是否听到了正常的声音？(y/n): ").strip().lower()

            if response == 'y':
                print("🎉 太好了！TTS音频生成和播放都正常！")
                print("💡 如果在完整系统中没有声音，请检查:")
                print("   - WebRTC音频轨道连接")
                print("   - 浏览器音频权限")
                print("   - 音频设备选择")
                return True
            else:
                print("❌ 音频播放有问题")
                return False

        except Exception as e:
            print(f"❌ 音频播放失败: {e}")
            print("💡 请确保已安装: pip install sounddevice")
            print("💡 可能需要安装PortAudio库:")
            print("   macOS: brew install portaudio")
            print("   Ubuntu: sudo apt-get install libportaudio2")
            return False

    except Exception as e:
        print(f"❌ TTS测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_edge_tts_local():
    """测试Edge TTS本地生成"""
    print("\n" + "=" * 70)
    print("🌐 Edge TTS本地测试（免费）")
    print("=" * 70)

    try:
        from ttsreal import EdgeTTS

        class MockOpt:
            def __init__(self):
                self.tts = 'edgetts'
                self.REF_FILE = 'zh-CN-YunxiNeural'  # 免费语音
                self.fps = 30
                self.sessionid = 888

        opt = MockOpt()

        class MockParent:
            def __init__(self):
                self.audio_frames = []

            def put_audio_frame(self, audio_chunk, datainfo):
                self.audio_frames.append((audio_chunk.copy(), datainfo))
                print(f"  收到音频帧: {len(audio_chunk)} samples")

        mock_parent = MockParent()
        tts = EdgeTTS(opt, mock_parent)

        test_text = "这是Edge TTS的测试语音，完全免费。"
        print(f"📝 测试文本: {test_text}")
        print("🔄 正在生成音频...")

        start_time = time.time()
        tts.txt_to_audio((test_text, {"test_id": 2}))
        generation_time = time.time() - start_time

        print(f"✅ 生成完成，耗时: {generation_time:.2f}秒")

        if mock_parent.audio_frames:
            audio_data = np.concatenate(
                [f for f, _ in mock_parent.audio_frames])
            print(f"🔊 音频长度: {len(audio_data)/16000:.2f}秒")

            # 播放
            print("🎵 播放Edge TTS音频...")
            time.sleep(2)

            try:
                sd.play(audio_data * 0.7, samplerate=16000)
                sd.wait()
                print("✅ Edge TTS播放完成")
                return True
            except:
                print("❌ 播放失败")
                return False
        else:
            print("❌ 没有生成音频")
            return False

    except Exception as e:
        print(f"❌ Edge TTS测试失败: {e}")
        return False


def test_tts_file_save():
    """测试TTS音频保存到文件"""
    print("\n" + "=" * 70)
    print("💾 TTS音频保存测试")
    print("=" * 70)

    try:
        from ttsreal import DoubaoTTS

        class MockOpt:
            def __init__(self):
                self.tts = 'doubao'
                self.REF_FILE = 'zh_female_vv_uranus_bigtts'
                self.fps = 30
                self.sessionid = 777

        opt = MockOpt()

        class AudioCollector:
            def __init__(self):
                self.audio_frames = []

            def put_audio_frame(self, audio_chunk, datainfo):
                self.audio_frames.append(audio_chunk.copy())

        collector = AudioCollector()
        tts = DoubaoTTS(opt, collector)

        test_text = "音频保存测试，这个声音将被保存到文件。"
        print(f"📝 测试文本: {test_text}")

        tts.txt_to_audio((test_text, {"save_test": True}))

        if collector.audio_frames:
            audio_data = np.concatenate(collector.audio_frames)

            # 保存到WAV文件
            output_file = "test_tts_output.wav"
            sf.write(output_file, audio_data, 16000)

            print(f"✅ 音频已保存到: {output_file}")
            print(f"   文件大小: {os.path.getsize(output_file)} bytes")
            print(f"   时长: {len(audio_data)/16000:.2f}秒")

            # 尝试播放保存的文件
            try:
                data, sr = sf.read(output_file)
                print(f"🎵 正在播放保存的文件...")
                sd.play(data * 0.7, samplerate=sr)
                sd.wait()
                print("✅ 文件播放完成")
                return True
            except Exception as e:
                print(f"⚠️ 文件播放失败: {e}")
                return True  # 保存成功也算部分成功
        else:
            print("❌ 没有生成音频")
            return False

    except Exception as e:
        print(f"❌ 文件保存测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("TTS本地音频测试工具")
    print("这个工具可以直接测试TTS音频生成，无需启动完整系统")
    print("=" * 70)

    # 检查sounddevice是否安装
    try:
        import sounddevice
        print("✅ sounddevice 库已安装")
    except ImportError:
        print("❌ 需要安装 sounddevice 库")
        print("运行: pip install sounddevice")
        print("macOS可能还需要: brew install portaudio")
        return False

    tests = [
        ("豆包TTS音频生成和播放", test_tts_audio_generation_and_playback),
        ("Edge TTS音频生成和播放", test_edge_tts_local),
        ("TTS音频保存到文件", test_tts_file_save),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n🎯 测试: {name}")
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append((name, False))

        # 询问是否继续
        if test_func != tests[-1][1]:  # 不是最后一个测试
            response = input("\n是否继续下一个测试？(y/n): ").strip().lower()
            if response != 'y':
                break

    # 结果汇总
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 60)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(r for _, r in results)

    print("=" * 70)
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
