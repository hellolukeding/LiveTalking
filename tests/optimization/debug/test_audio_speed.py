#!/usr/bin/env python3
"""
音频播放速度测试 - 验证TTS播放速度是否正常
"""

import asyncio
import time
from queue import Queue

import numpy as np


class MockAudioTrack:
    """模拟WebRTC音频轨道"""

    def __init__(self, maxsize=500):
        self._queue = Queue(maxsize=maxsize)
        self._loop = None

    def put_nowait(self, item):
        self._queue.put_nowait(item)

    def qsize(self):
        return self._queue.qsize()


class MockAudioFrame:
    """模拟音频帧"""

    def __init__(self, samples, sample_rate=16000):
        self.samples = samples
        self.sample_rate = sample_rate
        self.pts = 0
        self.time_base = None


def test_audio_speed():
    """测试音频播放速度"""
    print("音频播放速度测试")
    print("=" * 50)

    # 创建模拟音频轨道
    audio_track = MockAudioTrack(maxsize=500)

    # 模拟音频数据：20ms的音频帧
    chunk_size = 320  # 20ms at 16kHz
    sample_rate = 16000

    # 生成测试音频数据
    test_audio = np.random.randn(chunk_size).astype(np.float32)

    print(f"音频参数:")
    print(f"  采样率: {sample_rate} Hz")
    print(f"  帧大小: {chunk_size} samples")
    print(f"  帧时长: {chunk_size/sample_rate*1000:.1f} ms")
    print(f"  队列容量: {audio_track._queue.maxsize}")

    # 模拟音频发送过程
    print(f"\n开始模拟音频发送...")
    start_time = time.time()
    frames_sent = 0

    # 模拟发送100帧音频（2秒）
    for i in range(100):
        # 创建音频帧
        frame = MockAudioFrame(chunk_size, sample_rate)

        # 模拟WebRTC时间戳处理
        if not hasattr(audio_track, '_start'):
            audio_track._start = time.time()
            audio_track._timestamp = 0
            audio_track.current_frame_count = 0

        # 计算时间戳
        pts = audio_track._timestamp
        frame.pts = pts
        frame.time_base = 1 / sample_rate

        # 推进时间戳
        audio_track._timestamp += chunk_size
        audio_track.current_frame_count += 1

        # 计算期望时间（基于帧数）
        expected_time = audio_track._start + \
            (audio_track.current_frame_count * 0.02)
        wait_time = expected_time - time.time()

        # 等待（模拟时间控制）
        if wait_time > 0:
            time.sleep(wait_time)

        # 发送到队列
        try:
            audio_track.put_nowait((frame, {}))
            frames_sent += 1
        except:
            # 队列满，清理旧帧
            while audio_track._queue.qsize() > 50:
                try:
                    audio_track.get_nowait()
                except:
                    break
            audio_track.put_nowait((frame, {}))
            frames_sent += 1

        if i % 20 == 0:
            print(f"  已发送 {frames_sent} 帧，队列大小: {audio_track.qsize()}")

    elapsed = time.time() - start_time

    print(f"\n测试结果:")
    print(f"  发送帧数: {frames_sent}")
    print(f"  实际耗时: {elapsed:.3f}s")
    print(f"  期望耗时: {frames_sent * 0.02:.3f}s")
    print(f"  时间差: {elapsed - frames_sent * 0.02:.3f}s")
    print(f"  平均FPS: {frames_sent/elapsed:.2f}")
    print(f"  最终队列大小: {audio_track.qsize()}")

    # 评估结果
    expected_time = frames_sent * 0.02
    time_diff = abs(elapsed - expected_time)

    print(f"\n性能评估:")
    if time_diff < 0.1:
        print("✅ 播放速度正常")
    elif time_diff < 0.5:
        print("⚠️  播放速度略有偏差")
    else:
        print("❌ 播放速度异常")

    if audio_track.qsize() < 50:
        print("✅ 队列控制良好")
    else:
        print("⚠️  队列可能过大")

    print("\n关键指标:")
    print(f"1. 时间精度: {time_diff:.3f}s (应<0.1s)")
    print(f"2. 队列大小: {audio_track.qsize()} (应<50)")
    print(f"3. 处理速度: {frames_sent/elapsed:.2f} FPS (应≈50 FPS)")


if __name__ == "__main__":
    test_audio_speed()
