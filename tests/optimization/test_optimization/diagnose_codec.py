#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS 编解码诊断工具
分析音频处理流程中的每个阶段，找出卡顿和噪音问题
"""

import base64
import logging
import os
import sys
import time
import uuid
from io import BytesIO

import numpy as np
import requests
import resampy
import soundfile as sf

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CodecDiagnostic:
    """编解码诊断器"""

    def __init__(self):
        self.sample_rate = 16000
        self.chunk = 320  # 20ms
        self.stats = {}

    def log_stage(self, stage_name, data, **kwargs):
        """记录处理阶段信息"""
        if isinstance(data, np.ndarray):
            info = {
                'shape': data.shape,
                'dtype': data.dtype,
                'min': np.min(data) if len(data) > 0 else 0,
                'max': np.max(data) if len(data) > 0 else 0,
                'mean': np.mean(data) if len(data) > 0 else 0,
                'rms': np.sqrt(np.mean(data**2)) if len(data) > 0 else 0,
                'length': len(data),
                'duration': len(data) / self.sample_rate if len(data) > 0 else 0
            }
        else:
            info = {'type': type(data), 'value': data}

        info.update(kwargs)
        self.stats[stage_name] = info
        logger.info(f"[CODEC_DIAGNOSTIC] {stage_name}: {info}")

    def analyze_audio_quality(self, audio_chunk):
        """分析音频质量"""
        if len(audio_chunk) == 0:
            return {'quality': 'empty', 'issues': ['空音频']}

        peak = np.max(np.abs(audio_chunk))
        rms = np.sqrt(np.mean(audio_chunk**2))
        dynamic_range = peak / (rms + 1e-8)

        issues = []
        quality = 'good'

        # 检查削波
        if peak > 0.95:
            issues.append(f'削波风险 (peak={peak:.3f})')
            quality = 'poor'
        elif peak > 0.90:
            issues.append(f'接近削波 (peak={peak:.3f})')
            quality = 'fair'

        # 检查噪音
        if rms < 0.003:
            issues.append(f'静音/过低 (rms={rms:.4f})')
            quality = 'poor'
        elif rms > 0.3:
            issues.append(f'可能过载 (rms={rms:.4f})')
            quality = 'fair'

        # 检查动态范围
        if dynamic_range > 20:
            issues.append(f'动态范围过大 ({dynamic_range:.1f})')
        elif dynamic_range < 5:
            issues.append(f'动态范围过小 ({dynamic_range:.1f})')

        return {
            'quality': quality,
            'peak': peak,
            'rms': rms,
            'dynamic_range': dynamic_range,
            'issues': issues
        }

    def test_doubao_api(self, text):
        """测试Doubao API返回的原始音频"""
        logger.info(f"\n{'='*60}")
        logger.info("阶段1: Doubao API调用和原始音频获取")
        logger.info(f"{'='*60}")

        # 从环境变量获取配置
        appid = os.getenv("DOUBAO_APPID")
        token = os.getenv("DOUBAO_TOKEN")
        voice_id = os.getenv("DOUBAO_VOICE_ID", "BV001_STREAMING")

        if not appid or not token:
            logger.error("缺少Doubao配置: DOUBAO_APPID, DOUBAO_TOKEN")
            return None

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
                "text": text,
                "text_type": "plain",
                "operation": "query"
            }
        }

        start_time = time.time()
        try:
            response = requests.post(
                "https://openspeech.bytedance.com/api/v1/tts",
                json=request_json,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            api_time = time.time() - start_time

            if response.status_code != 200:
                logger.error(f"API错误: {response.status_code}")
                return None

            result = response.json()
            if result.get("code", 0) != 3000:
                logger.error(f"API业务错误: {result.get('message')}")
                return None

            # 获取base64音频
            audio_base64 = None
            if "data" in result:
                if isinstance(result["data"], dict):
                    audio_base64 = result["data"].get("audio")
                elif isinstance(result["data"], str):
                    audio_base64 = result["data"]

            if not audio_base64:
                logger.error("响应中没有音频数据")
                return None

            # 解码
            audio_bytes = base64.b64decode(audio_base64)
            self.log_stage("API响应", None,
                           api_time=api_time,
                           response_size=len(response.content),
                           audio_bytes_size=len(audio_bytes))

            return audio_bytes

        except Exception as e:
            logger.error(f"API调用异常: {e}")
            return None

    def test_decoding(self, audio_bytes):
        """测试音频解码"""
        logger.info(f"\n{'='*60}")
        logger.info("阶段2: Base64解码和格式转换")
        logger.info(f"{'='*60}")

        try:
            # 解码为numpy数组
            audio_array = np.frombuffer(
                audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0

            quality = self.analyze_audio_quality(audio_array)
            self.log_stage("解码后音频", audio_array, **quality)

            return audio_array

        except Exception as e:
            logger.error(f"解码异常: {e}")
            return None

    def test_resampling(self, audio_array):
        """测试重采样（如果需要）"""
        logger.info(f"\n{'='*60}")
        logger.info("阶段3: 重采样处理")
        logger.info(f"{'='*60}")

        # Doubao返回16kHz，通常不需要重采样
        # 但检查是否需要
        if len(audio_array) > 0:
            # 模拟重采样检查
            original_length = len(audio_array)

            # 如果需要重采样（这里假设不需要，但保留逻辑）
            needs_resample = False  # 16kHz -> 16kHz

            if needs_resample:
                logger.info("需要重采样")
                # 实际重采样代码
                pass
            else:
                logger.info("不需要重采样，跳过")
                resampled_array = audio_array

            quality = self.analyze_audio_quality(resampled_array)
            self.log_stage("重采样后", resampled_array, **quality)

            return resampled_array
        else:
            logger.error("空音频数组")
            return None

    def test_chunking(self, audio_array):
        """测试分块处理"""
        logger.info(f"\n{'='*60}")
        logger.info("阶段4: 分块处理和流式输出")
        logger.info(f"{'='*60}")

        total_frames = 0
        issues = []
        buffer = np.array([], dtype=np.float32)

        for i in range(0, len(audio_array), self.chunk):
            if i + self.chunk > len(audio_array):
                break

            chunk_data = audio_array[i:i+self.chunk]
            buffer = np.concatenate([buffer, chunk_data])

            # 检查完整块
            while len(buffer) >= self.chunk:
                complete_chunk = buffer[:self.chunk]
                buffer = buffer[self.chunk:]

                # 分析每个块
                quality = self.analyze_audio_quality(complete_chunk)
                if quality['quality'] in ['poor', 'fair']:
                    issues.append(f"块{total_frames}: {quality['issues']}")

                total_frames += 1

                # 模拟时间延迟
                time.sleep(self.chunk / self.sample_rate)

        # 处理剩余
        if len(buffer) > 0:
            padded_chunk = np.zeros(self.chunk, dtype=np.float32)
            padded_chunk[:len(buffer)] = buffer
            quality = self.analyze_audio_quality(padded_chunk)
            total_frames += 1

        self.log_stage("分块处理", audio_array,
                       total_frames=total_frames,
                       issues=issues)

        return total_frames

    def test_webRTC_conversion(self, audio_chunk):
        """测试WebRTC格式转换"""
        logger.info(f"\n{'='*60}")
        logger.info("阶段5: WebRTC格式转换")
        logger.info(f"{'='*60}")

        try:
            # 转换为16-bit PCM
            frame = (audio_chunk * 32767).astype(np.int16)
            frame_2d = frame.reshape(1, -1)

            self.log_stage("WebRTC转换", audio_chunk,
                           converted_shape=frame_2d.shape,
                           converted_dtype=frame_2d.dtype,
                           min=np.min(frame_2d),
                           max=np.max(frame_2d))

            return frame_2d

        except Exception as e:
            logger.error(f"WebRTC转换异常: {e}")
            return None

    def run_full_diagnostic(self, test_text="测试音频质量"):
        """运行完整诊断"""
        logger.info("🔍 开始DoubaoTTS编解码诊断")
        logger.info(f"测试文本: {test_text}")

        # 1. API调用
        audio_bytes = self.test_doubao_api(test_text)
        if not audio_bytes:
            logger.error("❌ API调用失败")
            return

        # 2. 解码
        audio_array = self.test_decoding(audio_bytes)
        if audio_array is None:
            logger.error("❌ 解码失败")
            return

        # 3. 重采样
        audio_resampled = self.test_resampling(audio_array)
        if audio_resampled is None:
            logger.error("❌ 重采样失败")
            return

        # 4. 分块
        total_frames = self.test_chunking(audio_resampled)

        # 5. WebRTC转换（测试第一个块）
        if len(audio_resampled) >= self.chunk:
            first_chunk = audio_resampled[:self.chunk]
            self.test_webRTC_conversion(first_chunk)

        # 总结
        logger.info(f"\n{'='*60}")
        logger.info("📊 诊断总结")
        logger.info(f"{'='*60}")

        for stage, info in self.stats.items():
            logger.info(f"{stage}:")
            for k, v in info.items():
                logger.info(f"  {k}: {v}")

        # 问题分析
        logger.info(f"\n{'='*60}")
        logger.info("🔍 问题分析")
        logger.info(f"{'='*60}")

        all_issues = []
        for stage, info in self.stats.items():
            if 'issues' in info and info['issues']:
                all_issues.extend(info['issues'])

        if all_issues:
            logger.warning("发现以下问题:")
            for issue in all_issues:
                logger.warning(f"  ⚠️  {issue}")
        else:
            logger.info("✅ 未发现明显问题")

        return self.stats


if __name__ == "__main__":
    diagnostic = CodecDiagnostic()
    diagnostic.run_full_diagnostic("这是一个测试，用于检查音频编解码质量")
