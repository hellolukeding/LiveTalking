#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS 问题分析器
直接分析代码流程，找出卡顿和噪音的根本原因
"""

import base64
import json
import os
import sys
import time
import uuid
from datetime import datetime

import numpy as np
import requests

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def log(message, level="INFO"):
    """统一日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [{level}] {message}")


def analyze_doubao_api_response():
    """分析Doubao API响应质量"""
    log("="*60)
    log("阶段1: Doubao API 响应分析")
    log("="*60)

    # 检查环境变量
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID", "BV001_STREAMING")

    if not appid or not token:
        log("❌ 缺少Doubao配置", "ERROR")
        return None

    log(f"AppID: {appid}")
    log(f"VoiceID: {voice_id}")

    # 构建测试请求
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
        log("发送API请求...")
        start_time = time.time()

        response = requests.post(
            "https://openspeech.bytedance.com/api/v1/tts",
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        api_time = time.time() - start_time
        log(f"API响应时间: {api_time:.2f}s")

        if response.status_code != 200:
            log(f"❌ HTTP错误: {response.status_code}", "ERROR")
            log(f"响应内容: {response.text}")
            return None

        result = response.json()
        log(f"API返回码: {result.get('code', 'N/A')}")

        if result.get("code", 0) != 3000:
            log(f"❌ API业务错误: {result.get('message')}", "ERROR")
            return None

        # 分析响应结构
        log("✅ API调用成功")
        log(f"完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")

        # 获取音频数据
        audio_base64 = None
        if "data" in result:
            if isinstance(result["data"], dict):
                audio_base64 = result["data"].get("audio")
            elif isinstance(result["data"], str):
                audio_base64 = result["data"]

        if not audio_base64:
            log("❌ 响应中没有音频数据", "ERROR")
            return None

        # 解码分析
        audio_bytes = base64.b64decode(audio_base64)
        log(f"音频数据大小: {len(audio_bytes)} bytes")

        # 转换为numpy数组分析
        audio_array = np.frombuffer(
            audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0
        log(f"音频数组形状: {audio_array.shape}")
        log(f"音频时长: {len(audio_array)/16000:.2f}秒")

        # 质量分析
        peak = np.max(np.abs(audio_array))
        rms = np.sqrt(np.mean(audio_array**2))
        log(f"峰值电平: {peak:.4f}")
        log(f"RMS电平: {rms:.4f}")

        if peak > 0.95:
            log("⚠️  检测到削波风险 (峰值过高)", "WARNING")
        elif peak > 0.90:
            log("⚠️  接近削波阈值", "WARNING")

        if rms < 0.003:
            log("⚠️  音频电平过低 (可能静音)", "WARNING")
        elif rms > 0.3:
            log("⚠️  音频电平过高 (可能过载)", "WARNING")

        return audio_array

    except Exception as e:
        log(f"❌ 请求异常: {e}", "ERROR")
        return None


def analyze_streaming_processing(audio_array):
    """分析流式处理过程"""
    log("="*60)
    log("阶段2: 流式处理分析")
    log("="*60)

    if audio_array is None or len(audio_array) == 0:
        log("❌ 无音频数据", "ERROR")
        return

    chunk_size = 320  # 20ms
    total_chunks = len(audio_array) // chunk_size
    log(f"总样本数: {len(audio_array)}")
    log(f"块大小: {chunk_size}")
    log(f"总块数: {total_chunks}")

    # 分析每个块的质量
    issues = []
    for i in range(total_chunks):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        chunk = audio_array[start_idx:end_idx]

        chunk_peak = np.max(np.abs(chunk))
        chunk_rms = np.sqrt(np.mean(chunk**2))

        # 检查问题
        if chunk_peak > 0.95:
            issues.append(f"块{i}: 削波风险 (peak={chunk_peak:.3f})")
        if chunk_rms < 0.002:
            issues.append(f"块{i}: 电平过低 (rms={chunk_rms:.4f})")
        if chunk_rms > 0.35:
            issues.append(f"块{i}: 电平过高 (rms={chunk_rms:.4f})")

    if issues:
        log(f"发现 {len(issues)} 个潜在问题:", "WARNING")
        for issue in issues[:10]:  # 只显示前10个
            log(f"  ⚠️  {issue}")
    else:
        log("✅ 流式处理正常，未发现明显问题")

    # 检查音频连续性
    log("检查音频连续性...")
    for i in range(min(10, total_chunks)):  # 检查前10个块
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        chunk = audio_array[start_idx:end_idx]

        if len(chunk) == chunk_size:
            log(f"块{i}: 长度={len(chunk)}, 峰值={np.max(np.abs(chunk)):.3f}, RMS={np.sqrt(np.mean(chunk**2)):.4f}")


def analyze_webRTC_conversion(audio_array):
    """分析WebRTC格式转换"""
    log("="*60)
    log("阶段3: WebRTC格式转换分析")
    log("="*60)

    if audio_array is None or len(audio_array) < 320:
        return

    # 取第一个块进行测试
    first_chunk = audio_array[:320]

    log(f"原始块 - 长度: {len(first_chunk)}, 类型: {first_chunk.dtype}")
    log(f"原始块 - 范围: [{np.min(first_chunk):.4f}, {np.max(first_chunk):.4f}]")

    # 模拟WebRTC转换过程
    try:
        # 转换为16-bit PCM
        frame_16bit = (first_chunk * 32767).astype(np.int16)
        log(f"16-bit PCM - 长度: {len(frame_16bit)}, 类型: {frame_16bit.dtype}")
        log(f"16-bit PCM - 范围: [{np.min(frame_16bit)}, {np.max(frame_16bit)}]")

        # 转换为2D数组
        frame_2d = frame_16bit.reshape(1, -1)
        log(f"2D数组 - 形状: {frame_2d.shape}")

        # 检查转换损失
        reconstructed = frame_16bit.astype(np.float32) / 32767.0
        loss = np.mean(np.abs(first_chunk - reconstructed))
        log(f"转换损失: {loss:.6f}")

        if loss > 0.0001:
            log("⚠️  转换损失较大，可能影响音质", "WARNING")
        else:
            log("✅ 转换损失在可接受范围内")

    except Exception as e:
        log(f"❌ 转换异常: {e}", "ERROR")


def analyze_ttsreal_flow():
    """分析ttsreal.py中的处理流程"""
    log("="*60)
    log("阶段4: ttsreal.py 处理流程分析")
    log("="*60)

    # 检查DoubaoTTS类的关键方法
    ttsreal_path = os.path.join(os.path.dirname(
        os.path.dirname(__file__)), "ttsreal.py")

    if not os.path.exists(ttsreal_path):
        log("❌ ttsreal.py 文件不存在", "ERROR")
        return

    with open(ttsreal_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查关键方法
    log("检查DoubaoTTS类的关键方法...")

    # 1. 检查txt_to_audio方法
    if "def txt_to_audio" in content:
        log("✅ 找到 txt_to_audio 方法")
    else:
        log("❌ 未找到 txt_to_audio 方法", "ERROR")

    # 2. 检查stream_audio方法
    if "def stream_audio" in content:
        log("✅ 找到 stream_audio 方法")
    else:
        log("❌ 未找到 stream_audio 方法", "ERROR")

    # 3. 检查优化器集成
    if "optimizer" in content:
        log("✅ 检测到优化器集成")
    else:
        log("⚠️  未检测到优化器集成")

    # 4. 检查音频处理逻辑
    if "np.frombuffer" in content:
        log("✅ 使用numpy处理音频数据")
    else:
        log("⚠️  未使用numpy处理音频")

    # 5. 检查时间控制
    if "time.sleep" in content:
        log("✅ 存在时间控制逻辑")
    else:
        log("⚠️  未找到时间控制")

    # 6. 检查WebRTC直接发送
    if "direct_to_webrtc" in content:
        log("✅ 支持直接发送到WebRTC")
    else:
        log("⚠️  不支持直接发送到WebRTC")

    # 7. 检查音频格式转换
    if "AudioFrame" in content:
        log("✅ 使用AudioFrame格式")
    else:
        log("⚠️  未使用AudioFrame")


def main():
    """主分析函数"""
    log("🔍 DoubaoTTS 问题深度分析")
    log("开始时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 1. 分析API响应
    audio_array = analyze_doubao_api_response()

    if audio_array is not None:
        # 2. 分析流式处理
        analyze_streaming_processing(audio_array)

        # 3. 分析WebRTC转换
        analyze_webRTC_conversion(audio_array)

    # 4. 分析代码流程
    analyze_ttsreal_flow()

    log("="*60)
    log("📊 分析总结")
    log("="*60)
    log("请根据上述分析结果判断问题所在:")
    log("1. 如果API阶段有问题 → 检查网络或Doubao服务")
    log("2. 如果流式处理有问题 → 检查音频块处理逻辑")
    log("3. 如果WebRTC转换有问题 → 检查格式转换代码")
    log("4. 如果代码流程有问题 → 检查ttsreal.py实现")
    log("\n建议:")
    log("- 检查优化器是否正确集成")
    log("- 确认音频块大小是否合适 (320 samples)")
    log("- 验证时间延迟控制是否正常")
    log("- 检查WebRTC队列是否溢出")


if __name__ == "__main__":
    main()
