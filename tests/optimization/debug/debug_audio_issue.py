#!/usr/bin/env python3
"""
调试音频播放速度问题
"""

import time
from queue import Queue

import numpy as np


# 模拟音频处理流程
class MockTTS:
    def __init__(self):
        self.chunk = 320  # 20ms at 16kHz

    def generate_audio(self, text):
        """模拟TTS生成音频"""
        print(f"TTS生成: {text}")
        # 生成1秒的音频数据（50帧）
        audio_data = np.random.randint(-32768,
                                       32767, size=16000, dtype=np.int16)
        return audio_data.astype(np.float32) / 32767.0


class MockASR:
    def __init__(self):
        self.queue = Queue()
        self.fps = 50  # 20ms per frame

    def put_audio_frame(self, audio_chunk):
        self.queue.put(audio_chunk)

    def get_audio_frame(self):
        try:
            return self.queue.get(timeout=0.1)
        except:
            return np.zeros(320, dtype=np.float32)


class MockWebRTC:
    def __init__(self):
        self.queue = Queue(maxsize=200)
        self._start = None
        self._timestamp = 0
        self.current_frame_count = 0
        self.audio_ptime = 0.020

    def put_frame(self, frame):
        try:
            self.queue.put_nowait(frame)
        except:
            print("WebRTC队列满，丢帧")

    def recv_frame(self):
        """模拟WebRTC接收"""
        if self._start is None:
            self._start = time.time()
            self._timestamp = 0
            self.current_frame_count = 0

        # 获取帧
        try:
            frame = self.queue.get(timeout=0.1)
        except:
            # 返回静音
            frame = np.zeros(320, dtype=np.float32)

        # 时间控制
        expected_time = self._start + \
            (self.current_frame_count * self.audio_ptime)
        wait_time = expected_time - time.time()

        if wait_time > 0:
            # 动态调整
            queue_size = self.queue.qsize()
            if queue_size > 40:
                wait_time = min(wait_time, 0.005)
            elif queue_size > 20:
                wait_time = min(wait_time, 0.01)

            if wait_time > 0:
                time.sleep(wait_time)

        self.current_frame_count += 1
        return frame


def test_audio_speed():
    """测试音频处理速度"""
    print("=== 音频速度测试 ===")

    tts = MockTTS()
    asr = MockASR()
    webrtc = MockWebRTC()

    # 模拟TTS生成音频
    audio_data = tts.generate_audio("测试文本")
    print(f"TTS生成音频长度: {len(audio_data)} samples")

    # 模拟音频分块处理
    chunks = []
    for i in range(0, len(audio_data), 320):
        chunk = audio_data[i:i+320]
        if len(chunk) == 320:
            chunks.append(chunk)

    print(f"音频分块数量: {len(chunks)}")

    # 模拟处理流程
    start_time = time.time()
    processed_frames = 0

    for i, chunk in enumerate(chunks):
        # TTS -> ASR
        asr.put_audio_frame(chunk)

        # ASR -> WebRTC
        audio_frame = asr.get_audio_frame()
        webrtc.put_frame(audio_frame)

        # WebRTC接收（带时间控制）
        webrtc.recv_frame()

        processed_frames += 1

        if i % 10 == 0:
            print(f"处理进度: {i}/{len(chunks)}, 队列大小: {webrtc.queue.qsize()}")

    elapsed = time.time() - start_time
    expected_time = len(chunks) * 0.020

    print(f"\n结果:")
    print(f"  处理帧数: {processed_frames}")
    print(f"  实际耗时: {elapsed:.3f}s")
    print(f"  期望耗时: {expected_time:.3f}s")
    print(f"  时间偏差: {elapsed - expected_time:.3f}s")
    print(f"  播放速度: {processed_frames/elapsed:.2f} FPS (期望: 50 FPS)")

    if abs(elapsed - expected_time) < 0.1:
        print("✅ 速度正常")
    else:
        print("❌ 速度异常")


if __name__ == "__main__":
    test_audio_speed()
