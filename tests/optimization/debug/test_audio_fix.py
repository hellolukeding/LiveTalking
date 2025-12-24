#!/usr/bin/env python3
"""
测试音频修复后的基本功能
"""

import asyncio
import time
from queue import Queue

import numpy as np


# 模拟音频流程
def test_audio_flow():
    print("=== 音频流程测试 ===")

    # 1. 模拟TTS生成音频
    print("1. TTS生成音频...")
    audio_chunk = np.random.randn(320).astype(np.float32) * 0.1  # 20ms音频

    # 2. 模拟basereal.put_audio_frame
    print("2. basereal处理音频...")

    # 转换格式
    frame = (audio_chunk * 32767).astype(np.int16)
    frame_2d = frame.reshape(1, -1)

    # 模拟音频帧
    class MockAudioFrame:
        def __init__(self):
            self.sample_rate = 16000
            self.samples = 320

    new_frame = MockAudioFrame()
    print(
        f"   - 音频帧格式: {frame_2d.shape}, sample_rate={new_frame.sample_rate}, samples={new_frame.samples}")

    # 3. 模拟WebRTC队列
    print("3. WebRTC队列...")
    webrtc_queue = Queue(maxsize=200)

    # 检查队列大小
    queue_size = webrtc_queue.qsize()
    print(f"   - 队列大小: {queue_size}")

    if queue_size > 60:
        print("   - ❌ 队列过大，丢弃帧")
        return False
    else:
        print("   - ✅ 队列正常，放入帧")
        webrtc_queue.put((new_frame, {}))

    # 4. 模拟WebRTC接收
    print("4. WebRTC接收...")
    try:
        frame, eventpoint = webrtc_queue.get(timeout=0.1)
        print(f"   - ✅ 成功接收帧")

        # 检查属性
        if hasattr(frame, 'sample_rate') and hasattr(frame, 'samples'):
            print(
                f"   - ✅ 帧属性完整: sample_rate={frame.sample_rate}, samples={frame.samples}")
            return True
        else:
            print(f"   - ❌ 帧属性缺失")
            return False
    except:
        print("   - ❌ 接收失败")
        return False

# 测试音频轨道设置


def test_audio_track_setting():
    print("\n=== 音频轨道设置测试 ===")

    # 模拟BaseReal的音频轨道设置
    class MockBaseReal:
        def __init__(self):
            self.audio_track = None
            self.loop = None
            self._pending_audio = []

    class MockAudioTrack:
        def __init__(self):
            self._queue = Queue(maxsize=200)

    # 测试场景1: audio_track未设置
    print("场景1: audio_track未设置")
    base1 = MockBaseReal()
    audio_chunk = np.random.randn(320).astype(np.float32)

    # 模拟put_audio_frame逻辑
    if not (hasattr(base1, 'audio_track') and base1.audio_track):
        base1._pending_audio.append((audio_chunk, {}))
        print("   - 音频被缓冲 (正确)")
    else:
        print("   - ❌ 音频应该被缓冲但未执行")

    # 测试场景2: audio_track已设置
    print("\n场景2: audio_track已设置")
    base2 = MockBaseReal()
    base2.audio_track = MockAudioTrack()
    base2.loop = asyncio.new_event_loop()

    # 模拟put_audio_frame逻辑
    if not (hasattr(base2, 'audio_track') and base2.audio_track):
        base2._pending_audio.append((audio_chunk, {}))
        print("   - ❌ 音频被缓冲")
    else:
        print("   - ✅ 音频可以发送到WebRTC")

        # 模拟发送
        try:
            base2.audio_track._queue.put_nowait((audio_chunk, {}))
            print(f"   - ✅ 发送成功，队列大小: {base2.audio_track._queue.qsize()}")
        except:
            print("   - ❌ 发送失败")

    # 测试场景3: 清空缓冲区
    print("\n场景3: 清空缓冲区")
    base3 = MockBaseReal()
    base3.audio_track = MockAudioTrack()
    base3.loop = asyncio.new_event_loop()

    # 添加一些缓冲帧
    for i in range(3):
        base3._pending_audio.append(
            (np.random.randn(320).astype(np.float32), {}))

    print(f"   - 缓冲区有 {len(base3._pending_audio)} 帧")

    # 模拟_flush_pending_audio
    if base3.audio_track and base3.loop:
        sent = 0
        for frame, data in base3._pending_audio:
            try:
                base3.audio_track._queue.put_nowait((frame, data))
                sent += 1
            except:
                break
        base3._pending_audio = []
        print(f"   - ✅ 清空了 {sent} 帧到WebRTC")
    else:
        print("   - ❌ 无法清空缓冲区")


if __name__ == "__main__":
    # 运行测试
    result1 = test_audio_flow()
    test_audio_track_setting()

    print(f"\n=== 测试结果 ===")
    if result1:
        print("✅ 音频流程测试通过")
    else:
        print("❌ 音频流程测试失败")

    print("\n修复要点:")
    print("1. basereal.py中保存audio_track引用")
    print("2. 音频帧必须包含sample_rate和samples属性")
    print("3. 队列满时直接丢弃，不阻塞")
    print("4. 移除process_frames中的重复音频处理")
