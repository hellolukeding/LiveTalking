#!/usr/bin/env python3
"""测试音频格式转换"""

import numpy as np
from av import AudioFrame


def test_conversion():
    # 模拟TTS返回的音频数据 (float32, range -1 to 1)
    tts_audio = np.array([0.1, 0.2, -0.1, -0.2, 0.0, 0.5], dtype=np.float32)
    print(
        f"1. TTS音频: {tts_audio.dtype}, 范围: [{tts_audio.min():.4f}, {tts_audio.max():.4f}]")

    # 转换为16-bit PCM
    frame = (tts_audio * 32767).astype(np.int16)
    print(f"2. 16-bit PCM: {frame.dtype}, 范围: [{frame.min()}, {frame.max()}]")

    # 创建AudioFrame
    frame_2d = frame.reshape(1, -1)
    audio_frame = AudioFrame.from_ndarray(
        frame_2d, layout='mono', format='s16')
    audio_frame.sample_rate = 16000

    print(
        f"3. AudioFrame: format={audio_frame.format}, layout={audio_frame.layout}")
    print(
        f"   sample_rate={audio_frame.sample_rate}, samples={audio_frame.samples}")

    # 模拟WebRTC接收
    if hasattr(audio_frame, 'to_ndarray'):
        received = audio_frame.to_ndarray()
        print(
            f"4. WebRTC接收: {received.dtype}, 范围: [{received.min()}, {received.max()}]")

        # 转换回float32
        received_float = received.astype(np.float32) / 32767.0
        print(
            f"5. 播放音频: {received_float.dtype}, 范围: [{received_float.min():.4f}, {received_float.max():.4f}]")

        # 检查是否一致
        diff = np.abs(tts_audio - received_float)
        print(f"6. 失真: 最大={diff.max():.6f}, 平均={diff.mean():.6f}")

        if diff.max() < 1e-5:
            print("✅ 格式转换正确")
        else:
            print("❌ 格式转换错误！")


def test_speed():
    """测试播放速度"""
    print("\n" + "="*50)
    print("速度测试")
    print("="*50)

    # 生成20ms的音频 (320样本)
    chunk_size = 320
    sample_rate = 16000

    # 生成1秒的测试音频
    duration = 1.0  # 秒
    total_samples = int(duration * sample_rate)

    # 生成正弦波作为测试
    t = np.arange(total_samples) / sample_rate
    test_audio = np.sin(2 * np.pi * 440 * t) * 0.3  # 440Hz, 30%振幅

    print(f"测试音频: {duration}秒, {total_samples}样本")
    print(f"预期块数: {total_samples // chunk_size}")

    # 分块
    chunks = []
    for i in range(0, total_samples, chunk_size):
        chunk = test_audio[i:i+chunk_size]
        if len(chunk) == chunk_size:
            chunks.append(chunk)

    print(f"实际块数: {len(chunks)}")
    print(f"每块时长: {chunk_size/sample_rate*1000:.1f}ms")

    # 检查是否有重复
    if len(chunks) > 1:
        similarity = np.corrcoef(chunks[0], chunks[1])[0, 1]
        print(f"相邻块相似度: {similarity:.4f}")
        if similarity > 0.9:
            print("⚠️ 可能存在重复处理")


if __name__ == "__main__":
    print("音频格式和速度测试")
    print("="*50)
    test_conversion()
    test_speed()
