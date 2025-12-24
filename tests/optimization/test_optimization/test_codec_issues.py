#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试DoubaoTTS编解码问题
验证优化器集成和音频处理流程
"""

import base64
import json
import os
import sys
import time
import uuid

import numpy as np
import requests

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_environment():
    """测试环境配置"""
    print("="*60)
    print("🔍 环境配置检查")
    print("="*60)

    # 检查环境变量
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID", "BV001_STREAMING")

    print(f"✅ DOUBAO_APPID: {appid}")
    print(f"✅ DOUBAO_TOKEN: {token[:10] if token else 'None'}...")
    print(f"✅ DOUBAO_VOICE_ID: {voice_id}")

    if not appid or not token:
        print("❌ 缺少必要配置")
        return False

    print("✅ 环境配置正常")
    return True


def test_doubao_api():
    """测试Doubao API调用"""
    print("\n" + "="*60)
    print("📡 测试Doubao API调用")
    print("="*60)

    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID", "BV001_STREAMING")

    test_text = "测试音频质量，检查噪音和卡顿问题"

    request_json = {
        "app": {
            "appid": appid,
            "token": token,
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": str(uuid.uuid4())
        },
        "audio": {
            "voice_type": voice_id,
            "encoding": "wav",
            "rate": 16000,
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": test_text,
            "text_type": "plain",
            "operation": "query"
        }
    }

    try:
        print("发送API请求...")
        start_time = time.time()

        response = requests.post(
            "https://openspeech.bytedance.com/api/v1/tts",
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        api_time = time.time() - start_time
        print(f"✅ API响应时间: {api_time:.2f}s")

        if response.status_code != 200:
            print(f"❌ HTTP错误: {response.status_code}")
            return None

        result = response.json()
        print(f"✅ API返回码: {result.get('code', 'N/A')}")

        if result.get("code", 0) != 3000:
            print(f"❌ API业务错误: {result.get('message')}")
            return None

        # 获取音频数据
        audio_base64 = None
        if "data" in result:
            if isinstance(result["data"], dict):
                audio_base64 = result["data"].get("audio")
            elif isinstance(result["data"], str):
                audio_base64 = result["data"]

        if not audio_base64:
            print("❌ 响应中没有音频数据")
            return None

        # 解码分析
        audio_bytes = base64.b64decode(audio_base64)
        print(f"✅ 音频数据大小: {len(audio_bytes)} bytes")

        # 转换为numpy数组
        audio_array = np.frombuffer(
            audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0
        print(f"✅ 音频数组形状: {audio_array.shape}")
        print(f"✅ 音频时长: {len(audio_array)/16000:.2f}秒")

        # 质量分析
        peak = np.max(np.abs(audio_array))
        rms = np.sqrt(np.mean(audio_array**2))
        print(f"✅ 峰值电平: {peak:.4f}")
        print(f"✅ RMS电平: {rms:.4f}")

        # 问题检查
        issues = []
        if peak > 0.95:
            issues.append("⚠️  削波风险 (峰值过高)")
        elif peak > 0.90:
            issues.append("⚠️  接近削波阈值")

        if rms < 0.003:
            issues.append("⚠️  音频电平过低")
        elif rms > 0.3:
            issues.append("⚠️  音频电平过高")

        if issues:
            print("\n⚠️  发现问题:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ API音频质量正常")

        return audio_array

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None


def test_chunk_analysis(audio_array):
    """测试音频块分析"""
    if audio_array is None:
        return

    print("\n" + "="*60)
    print("📦 音频块分析")
    print("="*60)

    chunk_size = 320
    total_chunks = len(audio_array) // chunk_size

    print(f"总样本数: {len(audio_array)}")
    print(f"块大小: {chunk_size}")
    print(f"总块数: {total_chunks}")

    # 分析前10个块
    issues = []
    for i in range(min(10, total_chunks)):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        chunk = audio_array[start_idx:end_idx]

        chunk_peak = np.max(np.abs(chunk))
        chunk_rms = np.sqrt(np.mean(chunk**2))

        print(f"块{i}: 峰值={chunk_peak:.3f}, RMS={chunk_rms:.4f}")

        if chunk_peak > 0.95:
            issues.append(f"块{i}: 削波风险")
        if chunk_rms < 0.002:
            issues.append(f"块{i}: 电平过低")
        if chunk_rms > 0.35:
            issues.append(f"块{i}: 电平过高")

    if issues:
        print(f"\n⚠️  发现 {len(issues)} 个块问题")
    else:
        print("✅ 音频块质量正常")


def test_optimizer_integration():
    """测试优化器集成"""
    print("\n" + "="*60)
    print("🔧 优化器集成测试")
    print("="*60)

    try:
        from test_optimization.combined_optimization import \
            CombinedAudioOptimizer
        print("✅ 成功导入优化器")

        # 检查ttsreal.py中的集成
        ttsreal_path = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), "ttsreal.py")
        with open(ttsreal_path, 'r', encoding='utf-8') as f:
            content = f.read()

        checks = {
            "自动集成方法": "_auto_integrate_optimizer" in content,
            "优化器初始化": "self.optimizer = None" in content,
            "CombinedAudioOptimizer导入": "CombinedAudioOptimizer" in content,
            "优化器使用": "self.optimizer.optimized_stream_audio" in content,
        }

        all_ok = True
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"{status} {check}: {result}")
            if not result:
                all_ok = False

        if all_ok:
            print("\n✅ 优化器集成完整")
        else:
            print("\n⚠️  优化器集成不完整")

        return all_ok

    except Exception as e:
        print(f"❌ 优化器导入失败: {e}")
        return False


def test_webRTC_conversion():
    """测试WebRTC格式转换"""
    print("\n" + "="*60)
    print("🌐 WebRTC格式转换测试")
    print("="*60)

    # 创建测试音频
    test_audio = np.random.randn(320).astype(np.float32) * 0.1
    test_audio = np.clip(test_audio, -0.5, 0.5)

    print(
        f"测试音频 - 长度: {len(test_audio)}, 范围: [{np.min(test_audio):.3f}, {np.max(test_audio):.3f}]")

    try:
        # 模拟转换过程
        frame_16bit = (test_audio * 32767).astype(np.int16)
        frame_2d = frame_16bit.reshape(1, -1)

        print(f"16-bit PCM - 长度: {len(frame_16bit)}, 类型: {frame_16bit.dtype}")
        print(f"2D数组 - 形状: {frame_2d.shape}")

        # 检查转换损失
        reconstructed = frame_16bit.astype(np.float32) / 32767.0
        loss = np.mean(np.abs(test_audio - reconstructed))
        print(f"转换损失: {loss:.6f}")

        if loss < 0.0001:
            print("✅ 转换损失在可接受范围内")
        else:
            print("⚠️  转换损失较大")

        # 检查是否有AudioFrame
        try:
            from av import AudioFrame
            audio_frame = AudioFrame.from_ndarray(
                frame_2d, layout='mono', format='s16')
            audio_frame.sample_rate = 16000
            print("✅ AudioFrame创建成功")
        except Exception as e:
            print(f"❌ AudioFrame创建失败: {e}")

    except Exception as e:
        print(f"❌ 转换测试失败: {e}")


def main():
    """主测试函数"""
    print("🔍 DoubaoTTS 编解码问题诊断")
    print("开始时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    # 1. 环境检查
    if not test_environment():
        print("\n❌ 环境配置错误，无法继续测试")
        return

    # 2. API测试
    audio_array = test_doubao_api()

    # 3. 音频块分析
    if audio_array is not None:
        test_chunk_analysis(audio_array)

    # 4. 优化器集成测试
    test_optimizer_integration()

    # 5. WebRTC转换测试
    test_webRTC_conversion()

    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    print("请根据上述结果判断问题:")
    print("1. 如果API阶段有问题 → 检查网络或Doubao服务")
    print("2. 如果音频块有问题 → 检查音频处理逻辑")
    print("3. 如果优化器未集成 → 检查ttsreal.py实现")
    print("4. 如果转换有问题 → 检查格式转换代码")
    print("\n建议:")
    print("- 确保优化器正确集成")
    print("- 检查音频块大小 (320 samples)")
    print("- 验证WebRTC队列状态")
    print("- 监控音频质量指标")


if __name__ == "__main__":
    main()
