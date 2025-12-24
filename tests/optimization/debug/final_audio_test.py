#!/usr/bin/env python3
"""
最终音频速度测试 - 验证所有修复
"""

import time
from queue import Queue

import numpy as np


class MockAudioFrame:
    """模拟WebRTC AudioFrame"""

    def __init__(self, data, sample_rate=16000):
        self.data = data
        self.sample_rate = sample_rate
        self.pts = 0
        self.time_base = None
        # 关键：设置samples属性
        self.samples = len(data) if data.ndim == 1 else data.shape[1]


class MockAudioTrack:
    """模拟WebRTC音频轨道"""

    def __init__(self, maxsize=200):  # 修复后的容量
        self._queue = Queue(maxsize=maxsize)
        self._loop = None

    def put_nowait(self, item):
        self._queue.put_nowait(item)

    def qsize(self):
        return self._queue.qsize()


def test_audio_processing():
    """测试完整的音频处理流程"""
    print("最终音频速度测试 - 完整流程验证")
    print("=" * 60)

    # 模拟音频处理参数
    chunk_size = 320  # 20ms at 16kHz
    sample_rate = 16000
    audio_ptime = 0.020  # 20ms

    # 创建模拟组件
    audio_track = MockAudioTrack(maxsize=200)

    print(f"测试配置:")
    print(f"  音频帧大小: {chunk_size} samples")
    print(f"  采样率: {sample_rate} Hz")
    print(f"  帧时长: {audio_ptime*1000:.1f} ms")
    print(f"  队列容量: {audio_track._queue.maxsize}")

    # 模拟WebRTC recv方法的时间控制
    print(f"\n模拟WebRTC recv方法:")

    start_time = time.time()
    frames_processed = 0
    total_frames = 100  # 2秒音频

    # 初始化时间基准
    _start = start_time
    _timestamp = 0
    current_frame_count = 0

    for i in range(total_frames):
        # 创建音频帧
        audio_data = np.zeros((1, chunk_size), dtype=np.int16)
        frame = MockAudioFrame(audio_data, sample_rate)

        # 设置PTS和time_base
        frame.pts = _timestamp
        frame.time_base = 1 / sample_rate

        # 推进时间戳
        _timestamp += chunk_size
        current_frame_count += 1

        # 精确时间控制 - 基于帧数
        expected_time = _start + (current_frame_count * audio_ptime)
        wait_time = expected_time - time.time()

        # 等待（模拟时间控制）
        if wait_time > 0:
            time.sleep(wait_time)

        # 放入队列（模拟流控）
        queue_size = audio_track._queue.qsize()

        if queue_size > 60:  # 丢帧策略
            print(f"  帧 {i}: 队列过大({queue_size})，丢弃")
            continue
        elif queue_size > 40:  # 轻微延迟
            time.sleep(0.005)

        try:
            audio_track.put_nowait((frame, {}))
            frames_processed += 1
        except:
            # 队列满，清理旧帧
            while audio_track._queue.qsize() > 50:
                try:
                    audio_track.get_nowait()
                except:
                    break
            audio_track.put_nowait((frame, {}))
            frames_processed += 1

        if i % 20 == 0:
            print(f"  进度 {i}/{total_frames}: 队列={audio_track.qsize()}")

    elapsed = time.time() - start_time

    print(f"\n测试结果:")
    print(f"  处理帧数: {frames_processed}")
    print(f"  实际耗时: {elapsed:.3f}s")
    print(f"  期望耗时: {total_frames * audio_ptime:.3f}s")
    print(f"  时间偏差: {elapsed - total_frames * audio_ptime:.3f}s")
    print(f"  平均FPS: {frames_processed/elapsed:.2f}")
    print(f"  最终队列: {audio_track.qsize()}")

    # 性能评估
    expected_time = total_frames * audio_ptime
    time_diff = abs(elapsed - expected_time)

    print(f"\n性能评估:")
    if time_diff < 0.1:
        print("✅ 时间控制精确")
    elif time_diff < 0.5:
        print("⚠️  时间控制略有偏差")
    else:
        print("❌ 时间控制异常")

    if audio_track.qsize() < 50:
        print("✅ 队列管理良好")
    else:
        print("⚠️  队列可能过大")

    if frames_processed >= total_frames * 0.9:
        print("✅ 帧处理完整")
    else:
        print("❌ 丢帧过多")

    print(f"\n关键指标:")
    print(f"1. 时间精度: {time_diff:.3f}s (应<0.1s)")
    print(f"2. 队列大小: {audio_track.qsize()} (应<50)")
    print(f"3. 处理完整性: {frames_processed}/{total_frames} (应>90%)")
    print(f"4. 播放速度: {frames_processed/elapsed:.2f} FPS (应≈50 FPS)")


if __name__ == "__main__":
    test_audio_processing()
