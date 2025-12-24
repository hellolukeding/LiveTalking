#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频质量优化测试 - 验证噪音和语音丢失修复效果
"""

import logging
import os
import sys

import numpy as np

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入优化器
try:
    from fixes.audio_quality_fix import (AudioBufferManager,
                                         AudioQualityOptimizer)
    print("✅ 成功导入音频质量优化器")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)


def test_noise_reduction():
    """测试降噪效果"""
    print("\n" + "=" * 70)
    print("🧪 测试1: 降噪效果")
    print("=" * 70)

    # 创建包含噪音的音频
    clean_audio = np.sin(np.linspace(0, 4*np.pi, 320)) * 0.5  # 干净信号
    noise = np.random.randn(320) * 0.02  # 噪音
    noisy_audio = clean_audio + noise

    optimizer = AudioQualityOptimizer()
    processed, _ = optimizer.process_audio(noisy_audio)

    # 分析
    original_noise = np.sqrt(np.mean(noise ** 2))
    processed_noise = np.sqrt(np.mean((processed - clean_audio) ** 2))
    noise_reduction = (1 - processed_noise / original_noise) * 100

    print(f"原始噪音RMS: {original_noise:.4f}")
    print(f"处理后噪音RMS: {processed_noise:.4f}")
    print(f"噪音降低: {noise_reduction:.1f}%")

    success = noise_reduction > 30
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def test_gain_control():
    """测试增益控制"""
    print("\n" + "=" * 70)
    print("🧪 测试2: 增益控制（小音量放大）")
    print("=" * 70)

    # 创建小音量音频
    quiet_audio = np.sin(np.linspace(0, 4*np.pi, 320)) * 0.15

    optimizer = AudioQualityOptimizer()
    processed, _ = optimizer.process_audio(quiet_audio)

    original_peak = np.max(np.abs(quiet_audio))
    processed_peak = np.max(np.abs(processed))
    gain_applied = processed_peak / original_peak

    print(f"原始峰值: {original_peak:.3f}")
    print(f"处理后峰值: {processed_peak:.3f}")
    print(f"增益倍数: {gain_applied:.1f}x")

    success = gain_applied >= 1.5
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def test_buffer_management():
    """测试缓冲区管理"""
    print("\n" + "=" * 70)
    print("🧪 测试3: 缓冲区管理（防止丢失）")
    print("=" * 70)

    buffer_manager = AudioBufferManager(max_size=50)

    # 快速推送大量帧
    frames_sent = 0
    frames_dropped = 0

    for i in range(100):
        audio_chunk = np.random.randn(320) * 0.3
        eventpoint = {'frame': i}

        if buffer_manager.push(audio_chunk, eventpoint):
            frames_sent += 1
        else:
            frames_dropped += 1

    # 弹出所有帧
    frames_received = 0
    while True:
        frame = buffer_manager.pop(timeout=0.1)
        if frame is None:
            break
        frames_received += 1

    status = buffer_manager.get_status()

    print(f"发送帧数: {frames_sent}")
    print(f"接收帧数: {frames_received}")
    print(f"丢弃帧数: {frames_dropped}")
    print(f"缓冲区溢出: {status['overflow_count']}")

    success = frames_received > 0 and frames_dropped < 20
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def test_silence_filter():
    """测试静音过滤"""
    print("\n" + "=" * 70)
    print("🧪 测试4: 静音过滤")
    print("=" * 70)

    # 创建包含静音的音频
    silence = np.zeros(160)
    signal = np.sin(np.linspace(0, 4*np.pi, 160)) * 0.5
    mixed = np.concatenate([silence, signal, silence])

    optimizer = AudioQualityOptimizer()
    processed, _ = optimizer.process_audio(mixed)

    # 分析静音部分
    silence_part = processed[:160]
    signal_part = processed[160:320]

    silence_level = np.max(np.abs(silence_part))
    signal_level = np.max(np.abs(signal_part))

    print(f"静音部分音量: {silence_level:.4f}")
    print(f"信号部分音量: {signal_level:.4f}")
    print(f"信噪比: {20 * np.log10(signal_level / max(silence_level, 1e-6)):.1f} dB")

    success = silence_level < 0.1 and signal_level > 0.3
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def test_clipping_prevention():
    """测试削波预防"""
    print("\n" + "=" * 70)
    print("🧪 测试5: 削波预防")
    print("=" * 70)

    # 创建可能削波的音频
    clipped_audio = np.random.randn(320) * 1.2  # 超过1.0，会削波

    optimizer = AudioQualityOptimizer()
    processed, _ = optimizer.process_audio(clipped_audio)

    original_peak = np.max(np.abs(clipped_audio))
    processed_peak = np.max(np.abs(processed))

    print(f"原始峰值: {original_peak:.3f}")
    print(f"处理后峰值: {processed_peak:.3f}")
    print(f"是否削波: {original_peak > 0.95}")
    print(f"是否保护: {processed_peak <= 0.95}")

    success = processed_peak <= 0.95
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def test_comprehensive_quality():
    """综合质量测试"""
    print("\n" + "=" * 70)
    print("🧪 测试6: 综合质量评估")
    print("=" * 70)

    # 模拟真实场景：小音量 + 噪音 + 静音
    signal = np.sin(np.linspace(0, 8*np.pi, 1600)) * 0.2  # 小音量信号
    noise = np.random.randn(1600) * 0.015  # 噪音
    silence = np.zeros(160)  # 静音

    # 组合
    audio = np.concatenate([
        signal[:400] + noise[:400],
        silence,
        signal[400:800] + noise[400:800],
        silence,
        signal[800:1200] + noise[800:1200],
        silence,
        signal[1200:1600] + noise[1200:1600]
    ])

    optimizer = AudioQualityOptimizer()

    # 分段处理
    processed = np.array([], dtype=np.float32)
    for i in range(0, len(audio), 320):
        chunk = audio[i:i+320]
        if len(chunk) == 320:
            processed_chunk, _ = optimizer.process_audio(chunk)
            processed = np.concatenate([processed, processed_chunk])

    # 评估
    report = optimizer.get_quality_report()

    print("质量报告:")
    print(f"  - 原始峰值: {report['original_peak']:.3f}")
    print(f"  - 处理后峰值: {report['processed_peak']:.3f}")
    print(f"  - 峰值提升: {report['peak_improvement']:.2f}x")
    print(f"  - 增益应用: {report['gain_ratio']:.1%}")
    print(f"  - 降噪应用: {report['noise_filter_ratio']:.1%}")
    print(f"  - 静音过滤: {report['silence_ratio']:.1%}")
    print(f"  - 削波次数: {report['clipped_frames']}")

    # 综合判断
    quality_score = (
        report['peak_improvement'] * 0.3 +
        (1 - report['silence_ratio']) * 0.3 +
        (1 - report['clipping_ratio']) * 0.4
    )

    print(f"\n综合质量分数: {quality_score:.2f}")
    success = quality_score > 0.6
    print(f"结果: {'✅ 通过' if success else '❌ 失败'}")
    return success


def main():
    """运行所有测试"""
    print("🔊 DoubaoTTS 音频质量优化测试套件")
    print("=" * 70)
    print("目标：解决噪音和语音丢失问题")
    print("=" * 70)

    tests = [
        test_noise_reduction,
        test_gain_control,
        test_buffer_management,
        test_silence_filter,
        test_clipping_prevention,
        test_comprehensive_quality
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            logger.error(f"测试 {test.__name__} 异常: {e}")
            results.append(False)

    print("\n" + "=" * 70)
    print("📊 测试总结")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\n总分: {passed}/{total} ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n🎉 所有测试通过！音频质量优化已成功应用")
        print("\n优化特性:")
        print("  • 降噪处理：去除背景噪音")
        print("  • 增益控制：放大音量")
        print("  • 缓冲区管理：防止语音丢失")
        print("  • 静音过滤：保持节奏")
        print("  • 削波预防：保护音频质量")
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，需要进一步优化")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
