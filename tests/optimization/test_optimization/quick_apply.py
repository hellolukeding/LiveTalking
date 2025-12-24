#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS 优化快速应用脚本

一键应用所有音频优化，解决噪音、语音丢失、音画同步等问题
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from logger import logger
    print("✅ 成功导入日志模块")
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    print("⚠️ 使用基础日志模块")


def apply_all_optimizations(tts_instance, lip_asr=None):
    """
    一键应用所有优化方案

    Args:
        tts_instance: DoubaoTTS实例
        lip_asr: 唇形驱动实例（可选）

    Returns:
        dict: 包含所有优化器的字典
    """
    print("\n" + "=" * 70)
    print("🚀 DoubaoTTS 一键优化应用")
    print("=" * 70)

    optimizers = {}

    # 1. 应用综合优化（推荐）
    try:
        from fixes.combined_optimization import apply_combined_optimization
        print("\n[1/3] 应用综合优化...")
        optimizers['combined'] = apply_combined_optimization(
            tts_instance, lip_asr)
        print("✅ 综合优化应用成功")
    except Exception as e:
        print(f"❌ 综合优化失败: {e}")
        optimizers['combined'] = None

    # 2. 应用音频质量优化（备用）
    try:
        from fixes.audio_quality_fix import apply_audio_quality_optimization
        print("\n[2/3] 应用音频质量优化...")
        optimizers['quality'] = apply_audio_quality_optimization(tts_instance)
        print("✅ 音频质量优化应用成功")
    except Exception as e:
        print(f"⚠️ 音频质量优化跳过: {e}")
        optimizers['quality'] = None

    # 3. 应用播放优化（备用）
    try:
        from fixes.optimize_doubao_playback import apply_optimization
        print("\n[3/3] 应用播放优化...")
        optimizers['playback'] = apply_optimization(tts_instance, lip_asr)
        print("✅ 播放优化应用成功")
    except Exception as e:
        print(f"⚠️ 播放优化跳过: {e}")
        optimizers['playback'] = None

    # 保存引用
    tts_instance.all_optimizers = optimizers

    print("\n" + "=" * 70)
    print("🎉 优化应用完成！")
    print("=" * 70)

    # 显示状态
    if optimizers['combined']:
        status = optimizers['combined'].get_status_report()
        print(f"\n📊 当前状态:")
        print(f"  • LipASR就绪: {status['lip_asr_ready']}")
        print(f"  • 音频轨道就绪: {status['audio_track_ready']}")
        print(
            f"  • 降噪功能: {'✅' if status['quality_config']['enable_denoise'] else '❌'}")
        print(
            f"  • 增益控制: {'✅' if status['quality_config']['enable_gain_control'] else '❌'}")
        print(
            f"  • 直接转发: {'✅' if status['buffer_config']['enable_direct_forward'] else '❌'}")

    print(f"\n💡 使用方法:")
    print(f"  优化器会自动在 stream_audio() 中工作")
    print(f"  查看日志: tail -f livetalking.log")
    print(
        f"  获取状态: tts_instance.all_optimizers['combined'].get_status_report()")

    return optimizers


def verify_optimization(tts_instance):
    """验证优化是否生效"""
    print("\n" + "=" * 70)
    print("🔍 验证优化效果")
    print("=" * 70)

    if not hasattr(tts_instance, 'all_optimizers'):
        print("❌ 未找到优化器，请先应用优化")
        return False

    combined = tts_instance.all_optimizers.get('combined')
    if not combined:
        print("❌ 综合优化器未就绪")
        return False

    # 检查状态
    status = combined.get_status_report()

    checks = [
        ("LipASR就绪", status['lip_asr_ready']),
        ("音频轨道就绪", status['audio_track_ready']),
        ("有音频处理", status['stats']['total_frames'] > 0),
        ("有WebRTC输出", status['stats']['webrtc_frames'] > 0),
        ("有唇形驱动", status['stats']['lip_driven_frames'] > 0),
        ("丢失帧少", status['stats']['lost_frames'] < 10),
    ]

    print("\n检查结果:")
    all_passed = True
    for check_name, result in checks:
        status_icon = "✅" if result else "❌"
        print(f"  {status_icon} {check_name}")
        if not result:
            all_passed = False

    if all_passed:
        print("\n🎉 所有检查通过！优化已生效")
    else:
        print("\n⚠️ 部分检查未通过，请根据日志调整")

    return all_passed


def show_usage():
    """显示使用说明"""
    print("""
📋 使用说明

1. 基本使用:
   from fixes.quick_apply import apply_all_optimizations
   optimizers = apply_all_optimizations(tts_instance, lip_asr)

2. 验证优化:
   from fixes.quick_apply import verify_optimization
   verify_optimization(tts_instance)

3. 查看状态:
   status = tts_instance.all_optimizers['combined'].get_status_report()
   print(status)

4. 调整参数:
   optimizer = tts_instance.all_optimizers['combined']
   optimizer.quality_config['gain_factor'] = 2.0  # 增大音量
   optimizer.quality_config['noise_threshold'] = 0.005  # 更严格降噪

5. 监控日志:
   poetry run python app.py 2>&1 | grep -E "(COMBINED|AUDIO_QUALITY|BUFFER)"

🔧 常见问题:

Q: 噪音仍然很大？
A: 调整 optimizer.quality_config['noise_threshold'] = 0.005

Q: 语音仍然丢失？
A: 增大 optimizer.buffer_config['max_size'] = 300

Q: 唇形驱动无效？
A: 检查 lip_asr 是否正确传递，查看日志中的 LipASR 状态

Q: 音画不同步？
A: 减小 optimizer.buffer_config['max_size'] = 100 降低延迟
""")


if __name__ == "__main__":
    print("DoubaoTTS 优化快速应用脚本")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        show_usage()
    else:
        print("请在您的代码中使用:")
        print("  from fixes.quick_apply import apply_all_optimizations")
        print("  optimizers = apply_all_optimizations(tts, lip_asr)")
        print("\n或运行: python quick_apply.py --help 查看详细说明")
