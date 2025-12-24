#!/usr/bin/env python3
"""测试最终修复是否有效"""

from av import AudioFrame
import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, '/Users/lukeding/Desktop/playground/2025/LiveTalking')

# 设置环境变量（示例）
os.environ["DOUBAO_APPID"] = "your_appid"
os.environ["DOUBAO_TOKEN"] = "your_token"
os.environ["DOUBAO_VOICE_ID"] = "your_voice_id"


def test_audio_frame_creation():
    """测试AudioFrame创建"""
    print("测试AudioFrame创建...")

    # 模拟音频数据
    audio_chunk = np.random.rand(320).astype(np.float32) * 0.5

    # 转换为16-bit PCM
    frame = (audio_chunk * 32767).astype(np.int16)
    frame_2d = frame.reshape(1, -1)

    # 创建AudioFrame
    try:
        audio_frame = AudioFrame.from_ndarray(
            frame_2d, layout='mono', format='s16')
        audio_frame.sample_rate = 16000
        print(
            f"✅ AudioFrame创建成功: format={audio_frame.format}, sample_rate={audio_frame.sample_rate}")
        return True
    except Exception as e:
        print(f"❌ AudioFrame创建失败: {e}")
        return False


def test_doubao_tts_import():
    """测试DoubaoTTS导入"""
    print("\n测试DoubaoTTS导入...")

    try:
        from ttsreal import BaseTTS, DoubaoTTS, State
        print("✅ DoubaoTTS导入成功")
        return True
    except Exception as e:
        print(f"❌ DoubaoTTS导入失败: {e}")
        return False


def test_direct_to_webrtc_logic():
    """测试直接发送逻辑"""
    print("\n测试直接发送逻辑...")

    try:
        from ttsreal import DoubaoTTS

        # 创建模拟的opt对象
        class MockOpt:
            fps = 50
            REF_FILE = "test_voice"

        # 创建模拟的parent对象
        class MockParent:
            def put_audio_frame(self, chunk, event):
                print(f"  Parent收到音频: {len(chunk)}样本")

        # 创建TTS实例
        opt = MockOpt()
        parent = MockParent()
        tts = DoubaoTTS(opt, parent)

        # 设置直接发送标志
        tts.direct_to_webrtc = True
        tts.audio_track = None  # 模拟没有音频轨道
        tts.loop = None

        # 模拟音频数据
        audio_array = np.random.rand(640).astype(np.float32) * 0.3

        # 测试stream_audio方法
        print("  调用stream_audio...")
        tts.stream_audio(audio_array, ("测试文本", {}))

        print("✅ 直接发送逻辑测试完成")
        return True

    except Exception as e:
        print(f"❌ 直接发送逻辑测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("LiveTalking TTS 最终修复测试")
    print("=" * 60)

    results = []

    # 测试1: AudioFrame创建
    results.append(test_audio_frame_creation())

    # 测试2: DoubaoTTS导入
    results.append(test_doubao_tts_import())

    # 测试3: 直接发送逻辑
    results.append(test_direct_to_webrtc_logic())

    print("\n" + "=" * 60)
    print("测试结果总结:")
    print("=" * 60)

    if all(results):
        print("✅ 所有测试通过！修复成功！")
        print("\n现在您可以:")
        print("1. 重启LiveTalking应用")
        print("2. 测试TTS功能")
        print("3. 检查音频是否正常播放")
    else:
        print("❌ 部分测试失败")
        print(f"通过: {sum(results)}/{len(results)}")

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
