#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试超强力噪音消除效果
验证针对"噪音仍然过大"的解决方案
"""

import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_realistic_noisy_audio():
    """创建更真实的噪音音频 - 模拟实际问题"""
    print("创建真实噪音音频...")

    duration = 3.0
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration))

    # 1. 语音信号 (真实语音特征)
    speech = np.zeros(len(t))

    # 语音段1 (0.5-1.2秒)
    t1 = t[(t >= 0.5) & (t < 1.2)]
    speech1 = np.sin(2 * np.pi * 280 * t1) * 0.3  # 基频
    speech1 += np.sin(2 * np.pi * 560 * t1) * 0.15  # 二次谐波
    speech1 += np.sin(2 * np.pi * 840 * t1) * 0.08  # 三次谐波
    speech[(t >= 0.5) & (t < 1.2)] = speech1

    # 语音段2 (1.8-2.5秒)
    t2 = t[(t >= 1.8) & (t < 2.5)]
    speech2 = np.sin(2 * np.pi * 320 * t2) * 0.28
    speech2 += np.sin(2 * np.pi * 640 * t2) * 0.12
    speech2 += np.sin(2 * np.pi * 960 * t2) * 0.06
    speech[(t >= 1.8) & (t < 2.5)] = speech2

    # 2. 高频噪音 (主要问题)
    high_noise = np.random.randn(len(t)) * 0.08
    # 通过高通滤波增强高频
    high_noise = np.convolve(high_noise, [1, -0.9], mode='same')

    # 3. 低频嗡嗡声 (50Hz + 谐波)
    low_noise = np.sin(2 * np.pi * 50 * t) * 0.03
    low_noise += np.sin(2 * np.pi * 100 * t) * 0.015

    # 4. 随机脉冲噪音
    pulse_noise = np.zeros(len(t))
    for _ in range(30):
        idx = np.random.randint(0, len(t))
        duration = np.random.randint(5, 20)
        pulse_noise[idx:min(idx+duration, len(t))
                    ] = np.random.randn(min(duration, len(t)-idx)) * 0.15

    # 5. 背景噪音 (持续的)
    bg_noise = np.random.randn(len(t)) * 0.02

    # 6. 组合所有噪音
    total_noise = high_noise + low_noise + pulse_noise + bg_noise

    # 7. 混合语音和噪音
    noisy_audio = speech + total_noise

    # 8. 添加削波 (模拟问题)
    noisy_audio = np.clip(noisy_audio, -0.9, 0.9)

    # 9. 音量过小 (模拟用户反馈)
    noisy_audio = noisy_audio * 0.6

    return noisy_audio, speech, total_noise


def analyze_detailed(audio, name):
    """详细分析音频特征"""
    peak = np.max(np.abs(audio))
    rms = np.sqrt(np.mean(audio ** 2))

    # 噪音水平分析
    threshold = np.percentile(np.abs(audio), 25)
    noise_mask = np.abs(audio) < threshold
    noise_level = np.sqrt(
        np.mean(audio[noise_mask] ** 2)) if np.sum(noise_mask) > 0 else 0

    speech_mask = np.abs(audio) > threshold
    speech_energy = np.sqrt(
        np.mean(audio[speech_mask] ** 2)) if np.sum(speech_mask) > 0 else 0

    # 高频能量 (3kHz以上)
    fft = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1/16000)
    high_freq_mask = freqs > 3000
    high_freq_energy = np.sqrt(
        np.mean(np.abs(fft[high_freq_mask]) ** 2)) if np.any(high_freq_mask) else 0

    # 信噪比
    snr = 20 * np.log10(speech_energy / (noise_level + 1e-10)
                        ) if noise_level > 0 else 999

    print(f"\n{name}:")
    print(f"  峰值: {peak:.4f}")
    print(f"  RMS: {rms:.4f}")
    print(f"  噪音水平: {noise_level:.4f}")
    print(f"  语音能量: {speech_energy:.4f}")
    print(f"  高频能量: {high_freq_energy:.4f}")
    print(f"  信噪比: {snr:.1f} dB")

    return {
        'peak': peak,
        'rms': rms,
        'noise_level': noise_level,
        'speech_energy': speech_energy,
        'high_freq_energy': high_freq_energy,
        'snr': snr
    }


def test_ultra_optimizer():
    """测试超强力噪音消除"""
    print("="*70)
    print("🔇 超强力噪音消除测试")
    print("="*70)

    try:
        from test_optimization.ultra_noise_reduction import \
            UltraNoiseReductionOptimizer
        print("✅ 成功导入超强力噪音消除优化器")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return

    # 创建测试音频
    print("\n1. 创建真实噪音音频...")
    noisy_audio, speech, noise = create_realistic_noisy_audio()

    # 详细分析
    print("\n2. 详细音频分析...")
    original_stats = analyze_detailed(noisy_audio, "原始音频")

    # 创建模拟TTS
    class MockTTS:
        def __init__(self):
            self.chunk = 320
            self.state = type('State', (), {'RUNNING': 0})()
            self.audio_track = None
            self.loop = None

    # 创建优化器
    print("\n3. 创建超强力优化器...")
    mock_tts = MockTTS()
    optimizer = UltraNoiseReductionOptimizer(mock_tts, None)

    # 测试单个块
    print("\n4. 测试单个块处理...")
    test_chunk = noisy_audio[8000:8320]  # 0.5秒左右的语音段

    print("\n原始块:")
    analyze_detailed(test_chunk, "测试块")

    processed_chunk = optimizer.apply_ultra_noise_reduction(test_chunk)

    print("\n处理后块:")
    processed_stats = analyze_detailed(processed_chunk, "处理后")

    # 计算改善
    if original_stats['rms'] > 0:
        improvement = (
            1 - processed_stats['rms'] / original_stats['rms']) * 100
        print(f"\n✅ 噪音降低: {improvement:.1f}%")

        if improvement > 50:
            print("🎉 效果卓越！噪音大幅降低")
        elif improvement > 30:
            print("👍 效果显著")
        else:
            print("⚠️ 效果一般")

    # 测试完整音频流
    print("\n5. 测试完整音频流...")
    total_frames = 0
    success_frames = 0

    for i in range(0, len(noisy_audio), 320):
        if i + 320 > len(noisy_audio):
            break

        chunk = noisy_audio[i:i+320]
        eventpoint = {'text': '测试'}

        if i == 0:
            eventpoint['status'] = 'start'
        elif i + 320 >= len(noisy_audio):
            eventpoint['status'] = 'end'

        success = optimizer.process_audio_frame(chunk, eventpoint)
        total_frames += 1
        if success:
            success_frames += 1

    print(f"\n处理结果: {success_frames}/{total_frames} 帧成功")

    # 输出统计
    print("\n6. 超强力优化器统计...")
    stats = optimizer.stats

    if len(stats['original_rms']) > 0:
        avg_original = np.mean(stats['original_rms'])
        avg_processed = np.mean(stats['processed_rms'])

        print(f"原始平均RMS: {avg_original:.5f}")
        print(f"处理后平均RMS: {avg_processed:.5f}")

        if avg_original > 0:
            total_reduction = (1 - avg_processed / avg_original) * 100
            print(f"总体噪音降低: {total_reduction:.1f}%")

        if len(stats['noise_reduced_ratio']) > 0:
            avg_frame_reduction = np.mean(stats['noise_reduced_ratio'])
            print(f"平均帧降低: {avg_frame_reduction:.1f}%")

        print(f"静音去除: {stats['silence_removed']}")
        print(f"噪音压制: {stats['noise_suppressed']} 次")
        print(f"语音增强: {stats['speech_enhanced']} 次")
        print(f"削波保护: {stats['clipped_frames']} 帧")

    # 效果评估
    print("\n7. 效果评估...")
    if len(stats['original_rms']) > 0:
        original_avg = np.mean(stats['original_rms'])
        processed_avg = np.mean(stats['processed_rms'])

        if original_avg > 0:
            improvement = (1 - processed_avg / original_avg) * 100

            print(f"✅ 最终改善: {improvement:.1f}%")

            if improvement > 60:
                print("🎉 完美解决！噪音问题彻底消除")
                print("   声音将变得非常清晰干净")
            elif improvement > 40:
                print("👍 显著改善！噪音大幅降低")
                print("   声音质量明显提升")
            elif improvement > 25:
                print("👌 有效改善")
                print("   噪音有所减少")
            else:
                print("⚠️ 改善有限")
                print("   可能需要进一步优化")

    print("\n" + "="*70)
    print("测试完成！")
    print("="*70)


def main():
    print("🔍 超强力噪音消除 - 效果验证")
    print("开始时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    test_ultra_optimizer()

    print("\n💡 使用说明:")
    print("1. 超强力优化器已集成到ttsreal.py")
    print("2. 系统启动时自动使用")
    print("3. 查看日志中的噪音降低百分比")
    print("4. 预期效果: 噪音降低40-70%")


if __name__ == "__main__":
    main()
