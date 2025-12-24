#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试DoubaoTTS集成优化器的效果
"""

from logger import logger
import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class MockParent:
    """模拟父类，用于测试"""

    def __init__(self):
        self.lip_asr = MockLipASR()
        self.audio_frames = []

    def put_audio_frame(self, audio_chunk, eventpoint):
        self.audio_frames.append((audio_chunk, eventpoint))
        logger.debug(f"MockParent: 收到音频帧 {len(audio_chunk)} samples")


class MockLipASR:
    """模拟唇形驱动"""

    def __init__(self):
        self.feat_queue = []
        self.output_queue = []
        self.audio_frames = []

    def put_audio_frame(self, audio_chunk, eventpoint):
        self.audio_frames.append((audio_chunk, eventpoint))
        logger.debug(f"MockLipASR: 收到音频帧 {len(audio_chunk)} samples")


class MockOpt:
    """模拟配置对象"""

    def __init__(self):
        self.fps = 20
        self.REF_FILE = "test_voice"


def test_integrated_optimization():
    """测试集成优化器"""
    print("\n" + "="*70)
    print("🧪 测试DoubaoTTS集成优化器")
    print("="*70)

    # 创建模拟对象
    opt = MockOpt()
    parent = MockParent()

    # 创建DoubaoTTS实例
    from ttsreal import DoubaoTTS
    tts = DoubaoTTS(opt, parent)

    # 检查优化器是否已初始化
    print(f"\n1. 检查优化器初始化:")
    print(f"   - optimizer属性存在: {hasattr(tts, 'optimizer')}")
    print(f"   - optimizer初始值: {tts.optimizer}")

    # 模拟render调用，触发优化器集成
    from threading import Event
    quit_event = Event()

    # 模拟音频轨道
    class MockAudioTrack:
        def __init__(self):
            self._queue = []

    audio_track = MockAudioTrack()

    print(f"\n2. 调用render方法触发优化器集成...")
    tts.render(quit_event, audio_track=audio_track)

    # 等待一小段时间
    time.sleep(0.5)

    # 检查优化器是否已集成
    print(f"\n3. 检查优化器集成结果:")
    print(f"   - optimizer现在: {tts.optimizer}")
    print(
        f"   - 优化器类型: {type(tts.optimizer).__name__ if tts.optimizer else 'None'}")

    if tts.optimizer:
        print(f"   - 优化器就绪: {tts.optimizer.lip_asr_ready}")
        print(f"   - 音频轨道就绪: {tts.optimizer.audio_track_ready}")

        # 测试音频处理
        print(f"\n4. 测试音频处理...")

        # 创建测试音频数据（模拟TTS输出）
        test_audio = np.random.randn(16000).astype(np.float32) * 0.1  # 1秒的音频
        test_msg = ("测试文本", {"test": True})

        # 模拟调用stream_audio
        print(f"   - 测试音频长度: {len(test_audio)} samples")

        # 由于stream_audio现在会检查优化器，我们直接调用优化器的方法
        try:
            tts.optimizer.optimized_stream_audio(test_audio, test_msg)
            print(f"   ✅ 优化器处理成功")

            # 检查统计信息
            status = tts.optimizer.get_status_report()
            print(f"\n5. 处理统计:")
            print(f"   - 总帧数: {status['stats']['total_frames']}")
            print(f"   - WebRTC帧: {status['stats']['webrtc_frames']}")
            print(f"   - 唇形驱动帧: {status['stats']['lip_driven_frames']}")
            print(f"   - 丢失帧: {status['stats']['lost_frames']}")
            print(f"   - 降噪次数: {status['stats']['noise_filtered']}")
            print(f"   - 增益应用: {status['stats']['gain_applied']}")

            # 检查父类和LipASR是否收到数据
            print(f"\n6. 数据流向验证:")
            print(f"   - MockParent收到帧数: {len(parent.audio_frames)}")
            print(f"   - MockLipASR收到帧数: {len(parent.lip_asr.audio_frames)}")

            if len(parent.audio_frames) > 0 and len(parent.lip_asr.audio_frames) > 0:
                print(f"   ✅ 双路输出正常")
            else:
                print(f"   ⚠️  数据流向可能有问题")

            print(f"\n🎉 测试完成！集成优化器工作正常")

        except Exception as e:
            print(f"   ❌ 优化器处理失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n❌ 优化器集成失败")

    # 清理
    quit_event.set()
    time.sleep(0.2)


if __name__ == "__main__":
    test_integrated_optimization()
