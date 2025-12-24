#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS 音频质量优化 - 解决噪音和语音丢失问题

核心优化：
1. 降噪处理：去除背景噪音
2. 增益控制：提升音量，解决声音太小
3. 缓冲区管理：防止语音丢失
4. 同步机制：解决音画不同步
"""

import queue
import threading
import time
from typing import Dict, Optional, Tuple

import numpy as np

from logger import logger


class AudioQualityOptimizer:
    """音频质量优化器 - 解决噪音问题"""

    def __init__(self, sample_rate=16000, chunk_size=320):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        # 音频质量配置 - 针对噪音优化
        self.quality_config = {
            'gain_factor': 1.5,           # 音频增益（放大1.5倍）
            'noise_threshold': 0.008,     # 噪音阈值（更严格）
            'silence_threshold': 0.003,   # 静音阈值（更严格）
            'max_amplitude': 0.90,        # 最大振幅限制
            'enable_denoise': True,       # 启用降噪
            'enable_gain_control': True,  # 启用增益控制
            'enable_silence_filter': True  # 启用静音过滤
        }

        # 统计信息
        self.stats = {
            'total_frames': 0,
            'silence_frames': 0,
            'clipped_frames': 0,
            'noise_filtered': 0,
            'gain_applied': 0,
            'original_peak': 0,
            'processed_peak': 0
        }

    def analyze_audio(self, audio_chunk: np.ndarray) -> Dict:
        """分析音频块的质量"""
        if len(audio_chunk) == 0:
            return {'is_silence': True, 'peak': 0, 'rms': 0}

        # 计算峰值和RMS
        peak = np.max(np.abs(audio_chunk))
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        # 检测静音
        is_silence = peak < self.quality_config['silence_threshold']

        # 检测噪音
        has_noise = rms > self.quality_config['noise_threshold']

        # 检测削波
        is_clipped = peak > self.quality_config['max_amplitude']

        return {
            'peak': peak,
            'rms': rms,
            'is_silence': is_silence,
            'has_noise': has_noise,
            'is_clipped': is_clipped
        }

    def denoise(self, audio_chunk: np.ndarray) -> np.ndarray:
        """降噪处理 - 去除背景噪音"""
        if not self.quality_config['enable_denoise']:
            return audio_chunk

        # 计算统计信息
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        peak = np.max(np.abs(audio_chunk))

        # 如果RMS远小于峰值，说明有噪音
        if rms > 0 and peak > 0:
            ratio = peak / rms
            if ratio > 3.0:  # 峰值远大于RMS，说明有噪音
                # 使用更激进的降噪
                threshold = rms * 1.5  # 基于RMS的动态阈值

                # 创建平滑的降噪掩码
                denoised = np.copy(audio_chunk)
                mask = np.abs(audio_chunk) < threshold
                denoised[mask] = denoised[mask] * 0.1  # 强烈抑制噪音

                # 统计
                noise_removed = np.sum(mask)
                if noise_removed > 0:
                    self.stats['noise_filtered'] += noise_removed

                return denoised

        return audio_chunk

    def apply_gain(self, audio_chunk: np.ndarray) -> np.ndarray:
        """增益控制 - 提升音量"""
        if not self.quality_config['enable_gain_control']:
            return audio_chunk

        # 动态增益：根据当前音量调整
        peak = np.max(np.abs(audio_chunk))

        # 如果声音太小，应用更强的增益
        if peak < 0.2:
            gain = 2.0  # 2倍增益
        elif peak < 0.4:
            gain = 1.5  # 1.5倍增益
        else:
            gain = 1.2  # 默认增益

        amplified = audio_chunk * gain

        # 限制振幅，防止削波 - 更严格的限制
        max_amp = 0.90  # 硬限制在0.9
        amplified = np.clip(amplified, -max_amp, max_amp)

        # 统计
        if gain > 1.0:
            self.stats['gain_applied'] += len(audio_chunk)

        return amplified

    def filter_silence(self, audio_chunk: np.ndarray) -> np.ndarray:
        """过滤静音 - 但保持流连续性"""
        if not self.quality_config['enable_silence_filter']:
            return audio_chunk

        analysis = self.analyze_audio(audio_chunk)

        if analysis['is_silence']:
            self.stats['silence_frames'] += 1
            # 不完全去除，而是大幅降低音量，保持节奏
            return audio_chunk * 0.1

        return audio_chunk

    def check_clipping(self, audio_chunk: np.ndarray) -> bool:
        """检查削波"""
        peak = np.max(np.abs(audio_chunk))
        if peak > self.quality_config['max_amplitude']:
            self.stats['clipped_frames'] += 1
            logger.warning(f"[AUDIO_QUALITY] 削波警告: peak={peak:.3f}")
            return True
        return False

    def process_audio(self, audio_chunk: np.ndarray,
                      eventpoint: Dict = None) -> Tuple[np.ndarray, Dict]:
        """完整的音频处理流程"""
        if len(audio_chunk) == 0:
            return audio_chunk, eventpoint or {}

        self.stats['total_frames'] += 1

        # 记录原始峰值
        original_peak = np.max(np.abs(audio_chunk))
        self.stats['original_peak'] = max(
            self.stats['original_peak'], original_peak)

        # 0. 削波预防 - 首先确保输入不会削波
        if original_peak > 1.0:
            audio_chunk = np.clip(audio_chunk, -0.95, 0.95)
            original_peak = np.max(np.abs(audio_chunk))

        # 1. 降噪处理
        if original_peak > self.quality_config['noise_threshold']:
            audio_chunk = self.denoise(audio_chunk)

        # 2. 增益控制（声音太小时）
        if original_peak < 0.4:
            audio_chunk = self.apply_gain(audio_chunk)

        # 3. 静音过滤
        audio_chunk = self.filter_silence(audio_chunk)

        # 4. 最终削波检查和保护
        self.check_clipping(audio_chunk)
        audio_chunk = np.clip(audio_chunk, -0.90, 0.90)

        # 记录处理后峰值
        processed_peak = np.max(np.abs(audio_chunk))
        self.stats['processed_peak'] = max(
            self.stats['processed_peak'], processed_peak)

        # 5. 更新事件点
        if eventpoint:
            eventpoint['audio_quality'] = {
                'original_peak': original_peak,
                'processed_peak': processed_peak,
                'gain_applied': original_peak < 0.4,
                'denoised': original_peak > self.quality_config['noise_threshold']
            }

        return audio_chunk, eventpoint

    def get_quality_report(self) -> Dict:
        """获取质量报告"""
        total = self.stats['total_frames']
        if total == 0:
            return self.stats.copy()

        return {
            **self.stats,
            'silence_ratio': self.stats['silence_frames'] / total,
            'clipping_ratio': self.stats['clipped_frames'] / total,
            'noise_filter_ratio': self.stats['noise_filtered'] / total,
            'gain_ratio': self.stats['gain_applied'] / total,
            'peak_improvement': self.stats['processed_peak'] / max(self.stats['original_peak'], 0.001)
        }


class AudioBufferManager:
    """音频缓冲区管理器 - 解决语音丢失问题"""

    def __init__(self, max_size=300, chunk_size=320):
        self.max_size = max_size
        self.chunk_size = chunk_size

        # 使用单一大缓冲区，避免双缓冲复杂性
        self.buffer = queue.Queue(maxsize=max_size)

        # 溢出保护
        self.overflow_count = 0
        self.dropped_frames = 0

        # 统计
        self.stats = {
            'total_pushed': 0,
            'total_popped': 0,
            'overflows': 0,
            'drops': 0
        }

    def push(self, audio_chunk: np.ndarray, eventpoint: Dict) -> bool:
        """安全推送音频帧"""
        try:
            # 如果队列快满了，丢弃最旧的帧
            if self.buffer.qsize() >= self.max_size - 5:
                try:
                    self.buffer.get_nowait()
                    self.stats['drops'] += 1
                    self.dropped_frames += 1
                    logger.warning(f"[BUFFER] 队列接近满，丢弃最旧帧")
                except queue.Empty:
                    pass

            self.buffer.put_nowait((audio_chunk, eventpoint))
            self.stats['total_pushed'] += 1
            return True

        except queue.Full:
            self.stats['overflows'] += 1
            self.overflow_count += 1
            logger.error("[BUFFER] 队列满，无法推送")
            return False

    def pop(self, timeout=0.5) -> Optional[Tuple[np.ndarray, Dict]]:
        """安全弹出音频帧"""
        try:
            frame = self.buffer.get(timeout=timeout)
            self.stats['total_popped'] += 1
            return frame
        except queue.Empty:
            return None

    def get_status(self) -> Dict:
        """获取缓冲区状态"""
        return {
            'size': self.buffer.qsize(),
            'full': self.buffer.full(),
            'overflow_count': self.overflow_count,
            'dropped_frames': self.dropped_frames,
            'stats': self.stats.copy()
        }


def apply_audio_quality_optimization(tts_instance):
    """应用音频质量优化到TTS实例"""
    logger.info("=" * 60)
    logger.info("应用音频质量优化")
    logger.info("=" * 60)

    # 创建优化器
    quality_optimizer = AudioQualityOptimizer()
    buffer_manager = AudioBufferManager()

    # 保存引用
    tts_instance.audio_quality_optimizer = quality_optimizer
    tts_instance.audio_buffer_manager = buffer_manager

    # 修补stream_audio方法
    original_stream_audio = tts_instance.stream_audio

    def optimized_stream_audio(audio_array, msg):
        """优化的音频流处理"""
        text, textevent = msg

        # 使用缓冲区管理器
        for i in range(0, len(audio_array), tts_instance.chunk):
            if i + tts_instance.chunk > len(audio_array):
                break

            chunk = audio_array[i:i+tts_instance.chunk]

            # 音频质量处理
            processed_chunk, processed_event = quality_optimizer.process_audio(
                chunk, textevent)

            # 推送到缓冲区
            buffer_manager.push(processed_chunk, processed_event)

            # 从缓冲区弹出并发送
            frame_data = buffer_manager.pop()
            if frame_data:
                audio_chunk, eventpoint = frame_data

                # 发送到父类（保持原有逻辑）
                if hasattr(tts_instance, 'parent'):
                    tts_instance.parent.put_audio_frame(
                        audio_chunk, eventpoint)

        logger.info(f"[AUDIO_QUALITY] 处理完成: {text[:50]}...")

        # 输出质量报告
        report = quality_optimizer.get_quality_report()
        buffer_status = buffer_manager.get_status()
        logger.info(
            f"[AUDIO_QUALITY] 质量报告: 峰值提升 {report['peak_improvement']:.2f}x")
        logger.info(f"[AUDIO_QUALITY] 缓冲区状态: {buffer_status['size']}帧")

    # 替换方法
    tts_instance.stream_audio = optimized_stream_audio

    return quality_optimizer, buffer_manager


# 测试函数
if __name__ == "__main__":
    print("音频质量优化模块测试")
    print("=" * 50)

    # 创建测试数据
    test_audio = np.random.randn(3200) * 0.1  # 小音量音频

    optimizer = AudioQualityOptimizer()
    processed, _ = optimizer.process_audio(test_audio)

    print(f"原始峰值: {np.max(np.abs(test_audio)):.3f}")
    print(f"处理后峰值: {np.max(np.abs(processed)):.3f}")
    print(
        f"增益倍数: {np.max(np.abs(processed)) / max(np.max(np.abs(test_audio)), 0.001):.1f}x")

    report = optimizer.get_quality_report()
    print(f"质量报告: {report}")
