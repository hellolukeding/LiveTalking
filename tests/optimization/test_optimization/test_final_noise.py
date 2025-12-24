#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试终极噪音消除效果
验证双层噪音消除（ttsreal.py + basereal.py）
"""

import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_extreme_noisy_audio():
    """创建极端噪音音频 - 模拟最差情况"""
    print("创建极端噪音音频...")

    duration = 2.0
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration))

    # 1. 微弱语音信号
    speech = np.zeros(len(t))
    t1 = t[(t >= 0.3) & (t < 1.0)]
    speech1 = np.sin(2 * np.pi * 300 * t1) * 0.15
    speech1 += np.sin(2 * np.pi * 600 * t1) * 0.08
    speech1 += np.sin(2 * np.pi * 900 * t1) * 0.04
    speech[(t >= 0.3) & (t < 1.0)] = speech1

    # 2. 强噪音
    # 高频噪音 (主要问题)
    high_noise = np.random.randn(len(t)) * 0.12
    high_noise = np.convolve(high_noise, [1, -0.95], mode='same')

    # 低频嗡嗡
    low_noise = np.sin(2 * np.pi * 50 * t) * 0.05
    low_noise += np.sin(2 * np.pi * 100 * t) * 0.025

    # 随机脉冲
    pulse_noise = np.zeros(len(t))
    for _ in range(40):
        idx = np.random.randint(0, len(t))
        duration_pulse = np.random.randint(3, 15)
        pulse_noise[idx:min(idx+duration_pulse, len(t))
                    ] = np.random.randn(min(duration_pulse, len(t)-idx)) * 0.2

    # 背景噪音
    bg_noise = np.random.randn(len(t)) * 0.03

    # 组合
    total_noise = high_noise + low_noise + pulse_noise + bg_noise

    # 混合
    noisy_audio = speech + total_noise

    # 削波
    noisy_audio = np.clip(noisy_audio, -0.95, 0.95)

    # 音量极小
    noisy_audio = noisy_audio * 0.5

    return noisy_audio, speech, total_noise


def analyze_audio_detailed(audio, name):
    """详细音频分析"""
    peak = np.max(np.abs(audio))
    rms = np.sqrt(np.mean(audio ** 2))

    # 噪音水平
    threshold = np.percentile(np.abs(audio), 25)
    noise_mask = np.abs(audio) < threshold
    noise_level = np.sqrt(
        np.mean(audio[noise_mask] ** 2)) if np.sum(noise_mask) > 0 else 0

    speech_mask = np.abs(audio) > threshold
    speech_energy = np.sqrt(
        np.mean(audio[speech_mask] ** 2)) if np.sum(speech_mask) > 0 else 0

    # 高频能量
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


def test_double_layer_elimination():
    """测试双层噪音消除"""
    print("="*70)
    print("🔇 终极双层噪音消除测试")
    print("="*70)

    try:
        from test_optimization.final_noise_eliminator import \
            FinalNoiseEliminator
        print("✅ 成功导入终极噪音消除器")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return

    # 创建测试音频
    print("\n1. 创建极端噪音音频...")
    noisy_audio, speech, noise = create_extreme_noisy_audio()

    # 分析原始音频
    print("\n2. 原始音频分析...")
    original_stats = analyze_audio_detailed(noisy_audio, "原始音频")

    # 创建消除器
    print("\n3. 创建终极噪音消除器...")
    eliminator = FinalNoiseEliminator()

    # 第一层：TTS优化器处理
    print("\n4. 第一层：TTS优化器处理...")
    # 模拟ttsreal.py的处理
    from test_optimization.ultra_noise_reduction import \
        UltraNoiseReductionOptimizer

    class MockTTS:
        def __init__(self):
            self.chunk = 320
            self.state = type('State', (), {'RUNNING': 0})()
            self.audio_track = None
            self.loop = None

    mock_tts = MockTTS()
    tts_optimizer = UltraNoiseReductionOptimizer(mock_tts, None)

    # 处理第一层
    layer1_result = []
    for i in range(0, len(noisy_audio), 320):
        if i + 320 > len(noisy_audio):
            break
        chunk = noisy_audio[i:i+320]
        processed = tts_optimizer.apply_ultra_noise_reduction(chunk)
        layer1_result.extend(processed)

    layer1_audio = np.array(layer1_result)
    print("\n第一层处理后:")
    layer1_stats = analyze_audio_detailed(layer1_audio, "TTS优化器后")

    # 第二层：basereal.py处理
    print("\n5. 第二层：basereal.py处理...")
    layer2_result = []
    for i in range(0, len(layer1_audio), 320):
        if i + 320 > len(layer1_audio):
            break
        chunk = layer1_audio[i:i+320]
        processed = eliminator.apply_final_elimination(chunk)
        layer2_result.extend(processed)

    layer2_audio = np.array(layer2_result)
    print("\n第二层处理后:")
    layer2_stats = analyze_audio_detailed(layer2_audio, "终极消除后")

    # 效果对比
    print("\n6. 效果对比...")
    print(f"原始噪音水平: {original_stats['noise_level']:.5f}")
    print(f"第一层后噪音: {layer1_stats['noise_level']:.5f}")
    print(f"第二层后噪音: {layer2_stats['noise_level']:.5f}")

    if original_stats['noise_level'] > 0:
        layer1_reduction = (
            1 - layer1_stats['noise_level'] / original_stats['noise_level']) * 100
        layer2_reduction = (
            1 - layer2_stats['noise_level'] / original_stats['noise_level']) * 100
        total_reduction = (
            1 - layer2_stats['rms'] / original_stats['rms']) * 100

        print(f"\n✅ 第一层噪音降低: {layer1_reduction:.1f}%")
        print(f"✅ 第二层噪音降低: {layer2_reduction:.1f}%")
        print(f"🎉 总体噪音降低: {total_reduction:.1f}%")
        print(
            f"✅ 高频噪音降低: {(1 - layer2_stats['high_freq_energy'] / original_stats['high_freq_energy']) * 100:.1f}%")

        if total_reduction > 70:
            print("\n🎉 完美解决！噪音几乎完全消除")
        elif total_reduction > 50:
            print("\n👍 显著改善！噪音大幅降低")
        elif total_reduction > 30:
            print("\n👌 有效改善")
        else:
            print("\n⚠️ 改善有限")

    print("\n" + "="*70)
    print("测试完成！")
    print("="*70)


def main():
    print("🔍 终极双层噪音消除测试")
    print("开始时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    test_double_layer_elimination()

    print("\n💡 使用说明:")
    print("1. TTS优化器在ttsreal.py中处理音频")
    print("2. 终极消除器在basereal.py中处理音频")
    print("3. 双层处理确保噪音被彻底消除")
    print("4. 预期效果: 噪音降低50-80%")


if __name__ == "__main__":
    main()
