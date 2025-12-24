#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试深度噪音消除效果
验证噪音减少的程度
"""

import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_noisy_test_audio():
    """创建测试音频 - 模拟噪音"""
    print("创建测试音频...")

    # 1. 语音信号 (0.2-0.4幅度)
    duration = 2.0  # 2秒
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration))

    # 语音信号 - 模拟语音波形
    speech = np.sin(2 * np.pi * 300 * t) * 0.3  # 300Hz基础
    speech += np.sin(2 * np.pi * 1000 * t) * 0.1  # 1000Hz谐波
    speech += np.sin(2 * np.pi * 2000 * t) * 0.05  # 2000Hz谐波

    # 2. 添加各种噪音
    # 高频噪音
    high_freq_noise = np.random.randn(len(t)) * 0.05
    high_freq_noise = np.convolve(high_freq_noise, np.ones(5)/5, mode='same')

    # 低频嗡嗡声
    low_freq_noise = np.sin(2 * np.pi * 50 * t) * 0.02

    # 随机脉冲噪音
    pulse_noise = np.zeros(len(t))
    for _ in range(20):
        idx = np.random.randint(0, len(t))
        pulse_noise[idx:idx+10] = np.random.randn(10) * 0.1

    # 3. 组合信号
    noisy_audio = speech + high_freq_noise + low_freq_noise + pulse_noise

    # 4. 添加一些削波（模拟问题）
    noisy_audio = np.clip(noisy_audio, -0.8, 0.8)

    return noisy_audio, speech, high_freq_noise, low_freq_noise, pulse_noise


def analyze_audio(name, audio):
    """分析音频特征"""
    peak = np.max(np.abs(audio))
    rms = np.sqrt(np.mean(audio ** 2))

    # 计算噪音水平（使用低能量部分）
    threshold = np.percentile(np.abs(audio), 25)
    noise_mask = np.abs(audio) < threshold
    noise_level = np.sqrt(
        np.mean(audio[noise_mask] ** 2)) if np.sum(noise_mask) > 0 else 0

    # 语音能量（高能量部分）
    speech_mask = np.abs(audio) > threshold
    speech_energy = np.sqrt(
        np.mean(audio[speech_mask] ** 2)) if np.sum(speech_mask) > 0 else 0

    # 信噪比
    snr = 20 * np.log10(speech_energy / (noise_level + 1e-10)
                        ) if noise_level > 0 else 999

    print(f"\n{name}:")
    print(f"  峰值: {peak:.4f}")
    print(f"  RMS: {rms:.4f}")
    print(f"  噪音水平: {noise_level:.4f}")
    print(f"  语音能量: {speech_energy:.4f}")
    print(f"  信噪比: {snr:.1f} dB")

    return {
        'peak': peak,
        'rms': rms,
        'noise_level': noise_level,
        'speech_energy': speech_energy,
        'snr': snr
    }


def test_deep_noise_optimizer():
    """测试深度噪音消除优化器"""
    print("="*70)
    print("🔇 深度噪音消除优化器测试")
    print("="*70)

    try:
        from test_optimization.deep_noise_reduction import \
            DeepNoiseReductionOptimizer
        print("✅ 成功导入深度噪音消除优化器")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return

    # 创建测试音频
    print("\n1. 创建测试音频...")
    noisy_audio, speech, high_freq, low_freq, pulse = create_noisy_test_audio()

    # 分析原始音频
    print("\n2. 分析原始音频...")
    original_stats = analyze_audio("原始音频", noisy_audio)

    # 创建模拟TTS实例
    class MockTTS:
        def __init__(self):
            self.chunk = 320
            self.state = type('State', (), {'RUNNING': 0})()
            self.audio_track = None
            self.loop = None

    # 创建优化器
    print("\n3. 创建优化器...")
    mock_tts = MockTTS()
    optimizer = DeepNoiseReductionOptimizer(mock_tts, None)

    # 测试单个块的处理
    print("\n4. 测试单个块处理...")
    test_chunk = noisy_audio[:320]

    # 分析原始块
    print("\n原始块分析:")
    analyze_audio("测试块", test_chunk)

    # 应用噪音消除
    processed_chunk = optimizer.apply_noise_reduction(test_chunk)

    print("\n处理后块分析:")
    processed_stats = analyze_audio("处理后块", processed_chunk)

    # 测试整个音频流
    print("\n5. 测试完整音频流处理...")

    # 模拟音频流处理
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

        # 处理帧
        success = optimizer.process_audio_frame(chunk, eventpoint)
        total_frames += 1
        if success:
            success_frames += 1

    print(f"\n处理结果: {success_frames}/{total_frames} 帧成功")

    # 输出优化器统计
    print("\n6. 优化器统计...")
    stats = optimizer.stats

    if len(stats['original_rms']) > 0:
        avg_original = np.mean(stats['original_rms'])
        avg_processed = np.mean(stats['processed_rms'])
        avg_noise = np.mean(stats['noise_level'])

        print(f"平均原始RMS: {avg_original:.4f}")
        print(f"平均处理后RMS: {avg_processed:.4f}")
        print(f"平均噪音水平: {avg_noise:.4f}")

        if avg_original > 0:
            reduction = (1 - avg_processed / avg_original) * 100
            print(f"噪音降低: {reduction:.1f}%")

        print(f"静音帧: {stats['silence_frames']}")
        print(f"噪音帧: {stats['noise_frames']}")
        print(f"语音帧: {stats['speech_frames']}")
        print(f"削波帧: {stats['clipped_frames']}")
        print(f"增益应用: {stats['gain_applied']}")
        print(f"噪音消除: {stats['noise_reduced']}")

    # 对比分析
    print("\n7. 效果对比...")
    if len(stats['original_rms']) > 0:
        original_avg = np.mean(stats['original_rms'])
        processed_avg = np.mean(stats['processed_rms'])

        if original_avg > 0:
            improvement = (1 - processed_avg / original_avg) * 100
            print(f"✅ 音频质量改善: {improvement:.1f}%")

            if improvement > 30:
                print("🎉 效果显著！噪音大幅降低")
            elif improvement > 15:
                print("👍 效果良好，噪音明显减少")
            else:
                print("⚠️  效果一般，可能需要调整参数")

    print("\n" + "="*70)
    print("测试完成！")
    print("="*70)


def main():
    """主函数"""
    print("🔍 DoubaoTTS 深度噪音消除测试")
    print("开始时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    test_deep_noise_optimizer()

    print("\n💡 使用建议:")
    print("1. 优化器会自动集成到ttsreal.py中")
    print("2. 在实际运行时查看日志中的噪音统计")
    print("3. 如果效果不够，可以调整优化器的配置参数")
    print("4. 监控WebRTC队列状态，确保没有溢出")


if __name__ == "__main__":
    main()
