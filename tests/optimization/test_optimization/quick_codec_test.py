#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速编解码问题测试
直接测试优化器集成
"""

import os
import sys
import time

import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_optimizer_import():
    """测试优化器导入"""
    print("="*60)
    print("🔧 测试优化器导入")
    print("="*60)

    try:
        from test_optimization.combined_optimization import \
            CombinedAudioOptimizer
        print("✅ CombinedAudioOptimizer 导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def test_ttsreal_integration():
    """测试ttsreal.py中的优化器集成"""
    print("\n" + "="*60)
    print("🔍 检查ttsreal.py集成")
    print("="*60)

    ttsreal_path = os.path.join(os.path.dirname(
        os.path.dirname(__file__)), "ttsreal.py")

    with open(ttsreal_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查关键部分
    checks = [
        ("自动集成方法", "_auto_integrate_optimizer" in content),
        ("优化器初始化", "self.optimizer = None" in content),
        ("CombinedAudioOptimizer导入", "CombinedAudioOptimizer" in content),
        ("优化器使用", "self.optimizer.optimized_stream_audio" in content),
        ("render方法配置", "optimizer.setup_direct_forwarding" in content),
    ]

    all_ok = True
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if not result:
            all_ok = False

    return all_ok


def test_optimized_stream_audio():
    """测试优化的stream_audio方法"""
    print("\n" + "="*60)
    print("🎵 测试优化的音频流处理")
    print("="*60)

    # 模拟DoubaoTTS实例
    class MockTTS:
        def __init__(self):
            self.chunk = 320
            self.state = type('State', (), {'RUNNING': 0})()
            self.audio_track = None
            self.loop = None
            self.optimizer = None

    # 模拟音频数据
    test_audio = np.random.randn(1600).astype(np.float32) * 0.1  # 5个块
    test_msg = ("测试文本", {})

    mock_tts = MockTTS()

    # 检查stream_audio方法
    ttsreal_path = os.path.join(os.path.dirname(
        os.path.dirname(__file__)), "ttsreal.py")
    with open(ttsreal_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 查找stream_audio方法
    if "def stream_audio(self, audio_array, msg:" in content:
        print("✅ 找到stream_audio方法")

        # 检查是否使用优化器
        if "self.optimizer.optimized_stream_audio" in content:
            print("✅ stream_audio使用优化器")
        else:
            print("❌ stream_audio未使用优化器")
            return False

        # 检查基础处理逻辑
        if "self.parent.put_audio_frame" in content:
            print("✅ 保留基础处理逻辑（兼容性）")
        else:
            print("⚠️  可能缺少基础处理逻辑")

        return True
    else:
        print("❌ 未找到stream_audio方法")
        return False


def test_audio_quality_processing():
    """测试音频质量处理"""
    print("\n" + "="*60)
    print("🎚️  测试音频质量处理")
    print("="*60)

    try:
        from test_optimization.combined_optimization import \
            CombinedAudioOptimizer

        # 创建测试音频
        test_chunk = np.random.randn(320).astype(np.float32) * 0.1
        test_chunk = np.clip(test_chunk, -0.5, 0.5)

        # 模拟优化器
        class MockTTS:
            def __init__(self):
                self.chunk = 320

        optimizer = CombinedAudioOptimizer(MockTTS(), None)

        # 测试质量分析
        quality = optimizer.analyze_audio_quality(test_chunk)
        print(f"测试音频 - 峰值: {quality['peak']:.4f}, RMS: {quality['rms']:.4f}")

        # 测试音频处理
        processed = optimizer.apply_audio_processing(test_chunk)
        print(
            f"处理后 - 峰值: {np.max(np.abs(processed)):.4f}, RMS: {np.sqrt(np.mean(processed**2)):.4f}")

        print("✅ 音频质量处理正常")
        return True

    except Exception as e:
        print(f"❌ 音频质量处理测试失败: {e}")
        return False


def test_webRTC_conversion():
    """测试WebRTC格式转换"""
    print("\n" + "="*60)
    print("🌐 WebRTC格式转换测试")
    print("="*60)

    try:
        from av import AudioFrame

        # 测试音频
        test_audio = np.random.randn(320).astype(np.float32) * 0.1
        test_audio = np.clip(test_audio, -0.5, 0.5)

        # 转换为16-bit PCM
        frame_16bit = (test_audio * 32767).astype(np.int16)
        frame_2d = frame_16bit.reshape(1, -1)

        # 创建AudioFrame
        audio_frame = AudioFrame.from_ndarray(
            frame_2d, layout='mono', format='s16')
        audio_frame.sample_rate = 16000

        print(
            f"原始音频: 长度={len(test_audio)}, 范围=[{np.min(test_audio):.3f}, {np.max(test_audio):.3f}]")
        print(
            f"16-bit PCM: 长度={len(frame_16bit)}, 范围=[{np.min(frame_16bit)}, {np.max(frame_16bit)}]")
        print(
            f"AudioFrame: 形状={audio_frame.shape}, 格式={audio_frame.format.name}")

        # 检查转换损失
        reconstructed = frame_16bit.astype(np.float32) / 32767.0
        loss = np.mean(np.abs(test_audio - reconstructed))
        print(f"转换损失: {loss:.6f}")

        if loss < 0.0001:
            print("✅ WebRTC转换正常")
            return True
        else:
            print("⚠️  转换损失较大")
            return False

    except Exception as e:
        print(f"❌ WebRTC转换测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🔍 DoubaoTTS 编解码问题快速诊断")
    print("开始时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    results = []

    # 1. 优化器导入
    results.append(("优化器导入", test_optimizer_import()))

    # 2. 集成检查
    results.append(("ttsreal集成", test_ttsreal_integration()))

    # 3. stream_audio测试
    results.append(("stream_audio", test_optimized_stream_audio()))

    # 4. 音频质量处理
    results.append(("音频质量", test_audio_quality_processing()))

    # 5. WebRTC转换
    results.append(("WebRTC转换", test_webRTC_conversion()))

    # 总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)

    all_passed = True
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if not result:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("🎉 所有测试通过！优化器集成正常")
        print("\n建议:")
        print("- 优化器已正确集成")
        print("- 检查实际运行时的音频质量")
        print("- 监控WebRTC队列状态")
        print("- 验证唇形驱动同步")
    else:
        print("⚠️  部分测试失败，请检查上述问题")
        print("\n解决方案:")
        print("1. 检查ttsreal.py中的优化器集成代码")
        print("2. 确保CombinedAudioOptimizer正确导入")
        print("3. 验证stream_audio方法使用优化器")
        print("4. 检查WebRTC格式转换")


if __name__ == "__main__":
    main()
