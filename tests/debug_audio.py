#!/usr/bin/env python3
"""
音频调试脚本 - 用于诊断TTS噪声问题
"""
import numpy as np
import wave
import os
import sys

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))

def analyze_audio_data(audio_array: np.ndarray, sample_rate: int = 16000):
    """分析音频数据"""
    print(f"\n=== 音频数据分析 ===")
    print(f"数据类型: {audio_array.dtype}")
    print(f"形状: {audio_array.shape}")
    print(f"采样率: {sample_rate} Hz")
    print(f"时长: {len(audio_array) / sample_rate:.2f} 秒")
    print(f"最小值: {audio_array.min():.6f}")
    print(f"最大值: {audio_array.max():.6f}")
    print(f"均值: {audio_array.mean():.6f}")
    print(f"标准差: {audio_array.std():.6f}")
    
    # 检查是否有异常值
    if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
        clipped = np.sum(np.abs(audio_array) > 1.0)
        if clipped > 0:
            print(f"⚠️ 警告: 有 {clipped} 个样本超出 [-1, 1] 范围!")
    
    # 检查是否有NaN或Inf
    nan_count = np.sum(np.isnan(audio_array))
    inf_count = np.sum(np.isinf(audio_array))
    if nan_count > 0:
        print(f"⚠️ 警告: 有 {nan_count} 个 NaN 值!")
    if inf_count > 0:
        print(f"⚠️ 警告: 有 {inf_count} 个 Inf 值!")
    
    # 检查静音段
    silence_threshold = 0.01
    silence_samples = np.sum(np.abs(audio_array) < silence_threshold)
    silence_ratio = silence_samples / len(audio_array) * 100
    print(f"静音比例: {silence_ratio:.1f}%")
    
    # 检查突变（可能导致噪声）
    if len(audio_array) > 1:
        diff = np.abs(np.diff(audio_array))
        max_diff = diff.max()
        large_jumps = np.sum(diff > 0.5)  # 大于0.5的跳变
        print(f"最大跳变: {max_diff:.6f}")
        if large_jumps > 0:
            print(f"⚠️ 警告: 有 {large_jumps} 个大跳变 (>0.5)，可能导致噪声!")

def save_debug_wav(audio_array: np.ndarray, filename: str, sample_rate: int = 16000):
    """保存音频为WAV文件用于调试"""
    # 转换为int16
    if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
        audio_int16 = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)
    else:
        audio_int16 = audio_array.astype(np.int16)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())
    
    print(f"✅ 已保存调试音频: {filename}")

def test_audio_conversion():
    """测试音频转换流程"""
    print("\n=== 测试音频转换流程 ===")
    
    # 生成测试音频（440Hz正弦波）
    sample_rate = 16000
    duration = 1.0  # 1秒
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio_float = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440Hz, 振幅0.5
    
    print("\n原始float32音频:")
    analyze_audio_data(audio_float, sample_rate)
    
    # 模拟basereal.py中的转换
    frame = np.clip(audio_float * 32767, -32768, 32767).astype(np.int16)
    
    print("\n转换后int16音频:")
    analyze_audio_data(frame.astype(np.float32) / 32767, sample_rate)
    
    # 保存测试音频
    save_debug_wav(audio_float, 'test_sine_440hz.wav', sample_rate)

def test_chunk_boundary():
    """测试分块边界是否会产生噪声"""
    print("\n=== 测试分块边界 ===")
    
    sample_rate = 16000
    chunk_size = 320  # 20ms
    
    # 生成连续的正弦波
    duration = 0.1  # 100ms = 5个chunk
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    
    # 分块
    chunks = []
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        if len(chunk) == chunk_size:
            chunks.append(chunk)
    
    print(f"总共 {len(chunks)} 个chunk")
    
    # 检查chunk边界
    for i in range(len(chunks) - 1):
        end_val = chunks[i][-1]
        start_val = chunks[i+1][0]
        diff = abs(end_val - start_val)
        if diff > 0.1:
            print(f"⚠️ Chunk {i} -> {i+1} 边界跳变: {diff:.4f}")
    
    # 重新拼接
    reconstructed = np.concatenate(chunks)
    
    print("\n重建后的音频:")
    analyze_audio_data(reconstructed, sample_rate)
    
    # 比较原始和重建
    original_trimmed = audio[:len(reconstructed)]
    diff = np.abs(original_trimmed - reconstructed)
    print(f"重建误差最大值: {diff.max():.6f}")

if __name__ == '__main__':
    test_audio_conversion()
    test_chunk_boundary()
    print("\n✅ 测试完成")
