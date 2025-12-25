#!/usr/bin/env python3
"""
测试音频处理质量 - 检测电音问题
"""
import numpy as np
import wave
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def simulate_tts_chunks(duration_sec=2.0, freq=440):
    """模拟TTS输出的16kHz音频块"""
    sample_rate = 16000
    chunk_size = 320  # 20ms
    total_samples = int(duration_sec * sample_rate)
    
    # 生成连续的正弦波
    t = np.arange(total_samples) / sample_rate
    audio = np.sin(2 * np.pi * freq * t).astype(np.float32) * 0.5
    
    # 分割成chunks
    chunks = []
    for i in range(0, total_samples, chunk_size):
        chunk = audio[i:i+chunk_size]
        if len(chunk) == chunk_size:
            chunks.append(chunk)
    
    return chunks

def process_chunk_to_48k(chunk_16k, last_tail_16k, last_tail_48k):
    """模拟basereal.py中的处理"""
    from scipy.interpolate import interp1d
    
    float_frame = chunk_16k.copy()
    
    # 16kHz平滑
    fade_16k = 16
    if last_tail_16k is not None and len(last_tail_16k) >= fade_16k:
        jump = abs(float_frame[0] - last_tail_16k[-1])
        if jump > 0.05:
            w = np.linspace(0.0, 1.0, fade_16k, dtype=np.float32)
            float_frame[:fade_16k] = last_tail_16k[-fade_16k:] * (1 - w) + float_frame[:fade_16k] * w
    
    new_tail_16k = float_frame[-fade_16k:].copy()
    
    # 重采样到48kHz
    x_16k = np.arange(len(float_frame))
    x_48k = np.linspace(0, len(float_frame)-1, len(float_frame)*3)
    f = interp1d(x_16k, float_frame, kind='linear', fill_value='extrapolate')
    float_frame_48k = f(x_48k).astype(np.float32)
    
    # 48kHz平滑
    fade_48k = 48
    if last_tail_48k is not None and len(last_tail_48k) >= fade_48k:
        jump = abs(float_frame_48k[0] - last_tail_48k[-1])
        if jump > 0.03:
            w = np.linspace(0.0, 1.0, fade_48k, dtype=np.float32)
            float_frame_48k[:fade_48k] = last_tail_48k[-fade_48k:] * (1 - w) + float_frame_48k[:fade_48k] * w
    
    new_tail_48k = float_frame_48k[-fade_48k:].copy()
    
    # 转换为int16
    frame_int16 = np.clip(float_frame_48k * 32767, -32768, 32767).astype(np.int16)
    
    return frame_int16, new_tail_16k, new_tail_48k

def analyze_audio(audio_int16, sample_rate):
    """分析音频质量"""
    audio_float = audio_int16.astype(np.float32) / 32767.0
    
    print(f"\n=== 音频质量分析 ({sample_rate}Hz) ===")
    print(f"样本数: {len(audio_int16)}")
    print(f"时长: {len(audio_int16) / sample_rate:.2f} 秒")
    print(f"范围: [{audio_int16.min()}, {audio_int16.max()}]")
    
    # 检查跳变
    diff = np.abs(np.diff(audio_float))
    max_jump = diff.max()
    large_jumps = np.sum(diff > 0.1)
    
    print(f"最大跳变: {max_jump:.4f}")
    print(f"大跳变 (>0.1): {large_jumps}")
    
    if large_jumps > 0:
        jump_indices = np.where(diff > 0.1)[0]
        print(f"跳变位置: {jump_indices[:10]}...")
        
    # 检查是否有电音特征（高频噪声）
    from scipy import signal
    freqs, psd = signal.welch(audio_float, sample_rate, nperseg=1024)
    
    # 检查高频能量
    high_freq_mask = freqs > 6000
    high_freq_energy = np.sum(psd[high_freq_mask])
    total_energy = np.sum(psd)
    high_freq_ratio = high_freq_energy / total_energy if total_energy > 0 else 0
    
    print(f"高频能量比: {high_freq_ratio:.4f}")
    
    if max_jump < 0.15 and large_jumps < 10 and high_freq_ratio < 0.1:
        print("✅ 音频质量良好，应该没有明显电音")
    else:
        print("⚠️ 可能存在电音问题")
    
    return max_jump, large_jumps, high_freq_ratio

def main():
    print("=== 测试音频处理质量 ===\n")
    
    # 生成模拟TTS输出
    chunks_16k = simulate_tts_chunks(duration_sec=1.0, freq=440)
    print(f"生成 {len(chunks_16k)} 个16kHz chunks")
    
    # 处理每个chunk
    processed_chunks = []
    last_tail_16k = None
    last_tail_48k = None
    
    for i, chunk in enumerate(chunks_16k):
        processed, last_tail_16k, last_tail_48k = process_chunk_to_48k(
            chunk, last_tail_16k, last_tail_48k
        )
        processed_chunks.append(processed)
    
    # 合并
    audio_48k = np.concatenate(processed_chunks)
    print(f"处理后: {len(audio_48k)} 个48kHz样本")
    
    # 分析
    analyze_audio(audio_48k, 48000)
    
    # 保存测试音频
    output_file = "test_processed_audio.wav"
    with wave.open(output_file, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)
        wav_file.writeframes(audio_48k.tobytes())
    
    print(f"\n已保存测试音频: {output_file}")

if __name__ == '__main__':
    main()
