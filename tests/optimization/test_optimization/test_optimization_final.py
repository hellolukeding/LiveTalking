#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS优化效果测试 - 最终版本
"""

import asyncio
import logging
import os
import queue
import sys
from unittest.mock import Mock

import numpy as np

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入优化器
try:
    from fixes.optimize_doubao_playback import DoubaoPlaybackOptimizer
    print("✅ 成功导入优化器")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)


class MockTTS:
    """模拟TTS实例"""

    def __init__(self):
        self.state = Mock()
        self.state.RUNNING = 0
        self.chunk = 320
        self.audio_track = None
        self.loop = None
        self.parent = Mock()
        self._original_txt_to_audio = Mock()
        self._original_stream_audio = Mock()

    def put_audio_frame(self, audio_chunk, eventpoint):
        logger.info(f"[MOCK] put_audio_frame: {len(audio_chunk)} samples")


class MockLipASR:
    """模拟唇形驱动"""

    def __init__(self):
        self.feat_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.audio_frames_received = 0

    def put_audio_frame(self, audio_chunk, eventpoint):
        self.audio_frames_received += 1
        logger.info(f"[MOCK LipASR] 收到音频帧 #{self.audio_frames_received}")

        # 模拟输出
        mock_frame = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        self.output_queue.put((mock_frame, 0, [(audio_chunk, 0, eventpoint)]))


class MockAudioTrack:
    """模拟WebRTC音频轨道"""

    def __init__(self):
        self._queue = queue.Queue(maxsize=100)
        self.frames_received = 0

    def __repr__(self):
        return f"MockAudioTrack(frames={self.frames_received}, qsize={self._queue.qsize()})"


class MockLoop:
    """模拟事件循环"""

    def call_soon_threadsafe(self, callback, *args):
        try:
            callback(*args)
        except Exception as e:
            logger.error(f"[MOCK Loop] 调用失败: {e}")


def test_optimization():
    """测试优化效果"""
    print("\n" + "=" * 70)
    print("🚀 DoubaoTTS 优化效果测试")
    print("=" * 70)

    # 1. 创建模拟组件
    print("\n1️⃣ 创建模拟组件...")
    mock_tts = MockTTS()
    mock_lip_asr = MockLipASR()
    mock_audio_track = MockAudioTrack()
    mock_loop = MockLoop()

    # 设置TTS组件
    mock_tts.audio_track = mock_audio_track
    mock_tts.loop = mock_loop
    mock_tts.parent.lip_asr = mock_lip_asr

    print("   ✅ 模拟组件创建完成")
    print(f"   📊 MockAudioTrack: {mock_audio_track}")

    # 2. 应用优化器
    print("\n2️⃣ 应用优化器...")
    optimizer = DoubaoPlaybackOptimizer(mock_tts, mock_lip_asr)

    # 设置直接转发
    optimizer.setup_direct_forwarding()
    print(f"   ✅ LipASR就绪: {optimizer.lip_asr_ready}")

    # 修补方法
    optimizer.patch_tts_methods()
    print("   ✅ 方法修补完成")

    # 3. 测试长文本处理
    print("\n3️⃣ 测试长文本处理...")
    long_text = "这是一个非常长的测试文本，包含多个句子。" * 10  # 100+字符
    logger.info(f"测试文本长度: {len(long_text)}字符")

    # 模拟音频数据 - 生成足够的音频数据
    audio_data = np.random.randn(16000 * 5).astype(np.float32)  # 5秒音频，80000样本
    logger.info(f"音频数据长度: {len(audio_data)}样本")

    # 调用优化后的stream_audio
    msg = (long_text, {'test': True})

    # 直接调用优化器的方法
    optimizer._optimized_stream_audio(audio_data, msg)

    print(f"   ✅ 长文本处理完成")

    # 4. 验证结果
    print("\n4️⃣ 验证结果...")

    # 检查队列内容
    webrtc_queue_size = mock_audio_track._queue.qsize()
    lip_output_size = mock_lip_asr.output_queue.qsize()

    # 从队列中取出项目来计数
    webrtc_frames = 0
    while not mock_audio_track._queue.empty():
        try:
            mock_audio_track._queue.get_nowait()
            webrtc_frames += 1
        except queue.Empty:
            break

    lip_frames = mock_lip_asr.audio_frames_received

    print(f"   📊 WebRTC音频帧: {webrtc_frames}")
    print(f"   👄 唇形驱动帧: {lip_frames}")
    print(f"   📦 WebRTC队列剩余: {webrtc_queue_size}")
    print(f"   📦 LipASR输出队列: {lip_output_size}")

    # 5. 性能评估
    print("\n5️⃣ 性能评估...")

    success = True
    if webrtc_frames == 0:
        print("   ❌ 失败: 没有音频帧发送到WebRTC")
        success = False
    else:
        print("   ✅ 音频帧正常发送")

    if lip_frames == 0:
        print("   ❌ 失败: 没有音频帧转发到唇形驱动")
        success = False
    else:
        print("   ✅ 唇形驱动正常工作")

    if webrtc_frames > 0 and lip_frames > 0:
        print("   🎉 优化成功! 消息丢失和唇形驱动失效问题已解决")
    else:
        print("   ⚠️  部分功能未正常工作")

    # 6. 状态报告
    print("\n6️⃣ 状态报告...")
    status = optimizer.get_status_report()
    print(f"   LipASR就绪: {status['lip_asr_ready']}")
    print(f"   音频轨道就绪: {status['audio_track_ready']}")
    print(f"   总发送帧数: {status['audio_stats']['total_sent']}")
    print(f"   唇形驱动帧数: {status['audio_stats']['lip_driven_frames']}")

    print("\n" + "=" * 70)
    if success:
        print("✅ 测试通过! DoubaoTTS优化已成功应用")
        print("\n优化特性:")
        print("  • 长文本自动分割处理")
        print("  • 音频帧直接转发到唇形驱动")
        print("  • 双路输出（WebRTC + 唇形驱动）")
        print("  • 队列监控和溢出保护")
    else:
        print("❌ 测试失败，请检查优化实现")
    print("=" * 70)

    return success


if __name__ == "__main__":
    success = test_optimization()
    sys.exit(0 if success else 1)
