#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超强力噪音消除优化器
针对"噪音仍然过大"的终极解决方案
"""

import queue
import threading
import time
from typing import Dict

import numpy as np

from logger import logger


class UltraNoiseReductionOptimizer:
    """超强力噪音消除优化器"""

    def __init__(self, tts_instance, lip_asr=None):
        self.tts = tts_instance
        self.lip_asr = lip_asr

        # 🔥 超强力配置 - 专门针对噪音过大问题
        self.noise_config = {
            # 第一层：激进的噪音门限
            'noise_threshold': 0.001,      # 极严格的噪音阈值
            'noise_reduction_factor': 0.01,  # 压制99%的噪音

            # 第二层：高频消除
            'high_freq_cutoff': 3000,      # 更低的高频截止 (3kHz)
            'high_freq_reduction': 0.1,    # 高频压制90%

            # 第三层：多频段深度处理
            'enable_multiband': True,
            'num_bands': 8,                # 8个频段更精细
            'band_reduction': [             # 各频段压制比例
                1.0,   # 0-200Hz (保留语音基频)
                0.8,   # 200-500Hz (保留语音)
                0.5,   # 500-1000Hz (部分压制)
                0.3,   # 1000-2000Hz (强力压制)
                0.2,   # 2000-3000Hz (超强力压制)
                0.1,   # 3000-4000Hz (极强压制)
                0.05,  # 4000-6000Hz (几乎全压制)
                0.02,  # 6000-8000Hz (完全压制)
            ],

            # 第四层：语音增强
            'speech_enhancement': True,
            'speech_band': [300, 3400],    # 语音频段
            'speech_boost': 1.5,           # 语音增强1.5倍

            # 第五层：动态范围压缩
            'dynamic_compression': True,
            'compression_threshold': 0.02,  # 低电平压缩
            'compression_ratio': 3.0,      # 3:1压缩比

            # 第六层：增益控制（保守）
            'gain_control': True,
            'target_level': 0.12,          # 目标音量更低
            'max_gain': 1.0,               # 最大增益1.0倍（不放大）

            # 第七层：削波保护（严格）
            'clip_limit': 0.75,            # 严格削波限制
            'soft_clip': True,             # 启用软削波

            # 第八层：静音检测
            'silence_threshold': 0.0005,   # 超严格静音检测
            'min_speech_duration': 0.1,    # 最小语音持续时间

            # 第九层：噪音学习
            'noise_learning': True,        # 动态噪音学习
            'noise_history_size': 50,      # 噪音历史窗口
        }

        # 统计信息
        self.stats = {
            'total_frames': 0,
            'processed_frames': 0,
            'original_rms': [],
            'processed_rms': [],
            'noise_reduced_ratio': [],
            'clipped_frames': 0,
            'silence_removed': 0,
            'noise_suppressed': 0,
            'speech_enhanced': 0,
        }

        # 噪音历史（用于动态学习）
        self.noise_history = []

        logger.info("[ULTRA_NOISE] 超强力噪音消除优化器已初始化")

    def setup_direct_forwarding(self):
        """设置直接转发路径"""
        logger.info("[ULTRA_NOISE] 设置直接转发路径")

        # 检查唇形驱动
        if hasattr(self.tts, 'parent') and hasattr(self.tts.parent, 'lip_asr'):
            self.lip_asr = self.tts.parent.lip_asr
            if hasattr(self.lip_asr, 'feat_queue') and hasattr(self.lip_asr, 'output_queue'):
                logger.info("[ULTRA_NOISE] LipASR就绪")

        # 检查音频轨道
        if hasattr(self.tts, 'audio_track') and self.tts.audio_track:
            logger.info("[ULTRA_NOISE] 音频轨道就绪")

    def analyze_audio_quality(self, audio_chunk: np.ndarray) -> Dict:
        """深度音频分析"""
        if len(audio_chunk) == 0:
            return {'peak': 0, 'rms': 0, 'is_silence': True, 'noise_level': 0, 'speech_energy': 0}

        peak = np.max(np.abs(audio_chunk))
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        # 静音检测
        is_silence = peak < self.noise_config['silence_threshold']

        # 噪音水平（使用统计方法）
        if len(audio_chunk) > 0:
            threshold = np.percentile(np.abs(audio_chunk), 20)
            noise_mask = np.abs(audio_chunk) < threshold
            noise_level = np.sqrt(
                np.mean(audio_chunk[noise_mask] ** 2)) if np.sum(noise_mask) > 0 else 0

            speech_mask = np.abs(audio_chunk) > threshold
            speech_energy = np.sqrt(
                np.mean(audio_chunk[speech_mask] ** 2)) if np.sum(speech_mask) > 0 else 0
        else:
            noise_level = 0
            speech_energy = 0

        return {
            'peak': peak,
            'rms': rms,
            'is_silence': is_silence,
            'noise_level': noise_level,
            'speech_energy': speech_energy,
            'snr': speech_energy / (noise_level + 1e-10),
        }

    def apply_ultra_noise_reduction(self, audio_chunk: np.ndarray) -> np.ndarray:
        """应用超强力噪音消除"""
        processed = audio_chunk.copy()

        # 0. 输入保护
        if np.max(np.abs(processed)) > 1.0:
            processed = np.clip(processed, -0.95, 0.95)

        # 1. 静音检测和去除
        peak = np.max(np.abs(processed))
        if peak < self.noise_config['silence_threshold']:
            self.stats['silence_removed'] += 1
            return np.zeros_like(processed) * 0.005  # 几乎完全静音

        # 2. 激进噪音门限
        noise_mask = np.abs(processed) < self.noise_config['noise_threshold']
        processed[noise_mask] = processed[noise_mask] * \
            self.noise_config['noise_reduction_factor']
        self.stats['noise_suppressed'] += np.sum(noise_mask)

        # 3. 多频段深度处理
        if self.noise_config['enable_multiband']:
            processed = self._ultra_multiband_processing(processed)

        # 4. 高频强力消除
        processed = self._ultra_high_freq_reduction(processed)

        # 5. 语音增强
        if self.noise_config['speech_enhancement']:
            processed = self._ultra_speech_enhancement(processed)

        # 6. 动态范围压缩
        if self.noise_config['dynamic_compression']:
            processed = self._ultra_dynamic_compression(processed)

        # 7. 保守增益控制
        if self.noise_config['gain_control']:
            rms = np.sqrt(np.mean(processed ** 2))
            if rms > 0:
                target_rms = self.noise_config['target_level']
                current_gain = target_rms / rms
                current_gain = min(current_gain, self.noise_config['max_gain'])
                processed = processed * current_gain

        # 8. 严格削波保护
        processed = np.clip(
            processed, -self.noise_config['clip_limit'], self.noise_config['clip_limit'])

        # 9. 软削波
        if self.noise_config['soft_clip']:
            threshold = self.noise_config['clip_limit'] * 0.85
            mask = np.abs(processed) > threshold
            if np.any(mask):
                x = processed[mask]
                processed[mask] = np.sign(
                    x) * (1 - np.exp(-np.abs(x) / threshold)) * threshold

        return processed

    def _ultra_multiband_processing(self, audio_chunk: np.ndarray) -> np.ndarray:
        """超强力多频段处理"""
        fft = np.fft.rfft(audio_chunk)
        freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

        # 8个频段
        bands = [0, 200, 500, 1000, 2000, 3000, 4000, 6000, 8000]

        for i in range(len(bands) - 1):
            band_mask = (freqs >= bands[i]) & (freqs < bands[i+1])
            reduction = self.noise_config['band_reduction'][i]
            fft[band_mask] *= reduction

        processed = np.fft.irfft(fft, len(audio_chunk))
        if len(processed) != len(audio_chunk):
            processed = processed[:len(audio_chunk)]

        return processed

    def _ultra_high_freq_reduction(self, audio_chunk: np.ndarray) -> np.ndarray:
        """超强力高频消除"""
        cutoff = self.noise_config['high_freq_cutoff']
        sample_rate = 16000

        # 使用更陡峭的滤波器
        window_size = int(sample_rate / cutoff) * 2  # 更大的窗口
        if window_size % 2 == 0:
            window_size += 1

        if window_size > 3:
            # 使用Sinc滤波器（更陡峭）
            kernel = np.sinc(
                np.arange(-window_size//2, window_size//2+1) * cutoff / sample_rate)
            kernel = kernel / np.sum(kernel)

            processed = np.convolve(audio_chunk, kernel, mode='same')

            # 混合原始信号
            alpha = self.noise_config['high_freq_reduction']
            processed = alpha * processed + (1 - alpha) * audio_chunk
        else:
            processed = audio_chunk

        return processed

    def _ultra_speech_enhancement(self, audio_chunk: np.ndarray) -> np.ndarray:
        """超强力语音增强"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms > 0.005:  # 检测到语音
            fft = np.fft.rfft(audio_chunk)
            freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

            # 语音频段增强
            speech_band = self.noise_config['speech_band']
            speech_mask = (freqs >= speech_band[0]) & (freqs <= speech_band[1])

            if np.any(speech_mask):
                # 语音频段强力提升
                fft[speech_mask] *= self.noise_config['speech_boost']

                # 非语音频段强力压制
                non_speech_mask = ~speech_mask
                fft[non_speech_mask] *= 0.3  # 压制70%

                processed = np.fft.irfft(fft, len(audio_chunk))
                if len(processed) != len(audio_chunk):
                    processed = processed[:len(audio_chunk)]

                # 混合
                processed = 0.8 * processed + 0.2 * audio_chunk
                self.stats['speech_enhanced'] += 1
                return processed

        return audio_chunk

    def _ultra_dynamic_compression(self, audio_chunk: np.ndarray) -> np.ndarray:
        """超强力动态范围压缩"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms < self.noise_config['compression_threshold']:
            threshold = self.noise_config['compression_threshold']
            ratio = self.noise_config['compression_ratio']

            gain = np.ones_like(audio_chunk)
            low_mask = np.abs(audio_chunk) < threshold

            if np.any(low_mask):
                # 强力压缩
                gain[low_mask] = 1.0 + (ratio - 1.0) * (threshold -
                                                        np.abs(audio_chunk[low_mask])) / threshold
                gain[low_mask] = np.clip(gain[low_mask], 1.0, ratio)

            processed = audio_chunk * gain
            return processed

        return audio_chunk

    def process_audio_frame(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """处理单个音频帧"""
        self.stats['total_frames'] += 1

        # 分析原始音频
        original_quality = self.analyze_audio_quality(audio_chunk)
        self.stats['original_rms'].append(original_quality['rms'])

        # 应用超强力噪音消除
        processed_chunk = self.apply_ultra_noise_reduction(audio_chunk)

        # 分析处理后音频
        processed_quality = self.analyze_audio_quality(processed_chunk)
        self.stats['processed_rms'].append(processed_quality['rms'])

        # 计算噪音降低比例
        if original_quality['rms'] > 0:
            reduction_ratio = (
                1 - processed_quality['rms'] / original_quality['rms']) * 100
            self.stats['noise_reduced_ratio'].append(reduction_ratio)

        # 削波检测
        if np.max(np.abs(processed_chunk)) > 0.75:
            self.stats['clipped_frames'] += 1

        # 双路发送
        webrtc_ok = self.send_to_webrtc(processed_chunk, eventpoint)
        lip_ok = self.send_to_lip_asr(processed_chunk, eventpoint)

        if webrtc_ok or lip_ok:
            self.stats['processed_frames'] += 1

        return webrtc_ok or lip_ok

    def send_to_webrtc(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """发送到WebRTC"""
        if not (self.tts.audio_track and self.tts.loop):
            return False

        try:
            frame = (audio_chunk * 32767).astype(np.int16).reshape(1, -1)
            from av import AudioFrame
            audio_frame = AudioFrame.from_ndarray(
                frame, layout='mono', format='s16')
            audio_frame.sample_rate = 16000
            self.tts.audio_track._queue.put_nowait((audio_frame, eventpoint))
            return True
        except:
            return False

    def send_to_lip_asr(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """发送到唇形驱动"""
        if not (self.lip_asr and hasattr(self.lip_asr, 'put_audio_frame')):
            return False
        try:
            self.lip_asr.put_audio_frame(audio_chunk, eventpoint)
            return True
        except:
            return False

    def optimized_stream_audio(self, audio_array: np.ndarray, msg: tuple):
        """优化的音频流处理"""
        text, textevent = msg

        logger.info(f"[ULTRA_NOISE] 开始超强力处理音频流，长度: {len(audio_array)}")

        total_frames = 0
        success_frames = 0

        for i in range(0, len(audio_array), self.tts.chunk):
            if i + self.tts.chunk > len(audio_array):
                break

            chunk = audio_array[i:i+self.tts.chunk]
            eventpoint = {'text': text[:50]}

            if i == 0:
                eventpoint['status'] = 'start'
            elif i + self.tts.chunk >= len(audio_array):
                eventpoint['status'] = 'end'

            success = self.process_audio_frame(chunk, eventpoint)
            total_frames += 1
            if success:
                success_frames += 1

            time.sleep(0.01)

        # 输出详细统计
        self._log_detailed_statistics(total_frames, success_frames)

        return success_frames > 0

    def _log_detailed_statistics(self, total_frames, success_frames):
        """输出详细统计"""
        logger.info("="*70)
        logger.info("🔇 超强力噪音消除 - 详细统计")
        logger.info("="*70)
        logger.info(f"总帧数: {total_frames}, 成功: {success_frames}")

        if len(self.stats['original_rms']) > 0:
            avg_original = np.mean(self.stats['original_rms'])
            avg_processed = np.mean(self.stats['processed_rms'])

            logger.info(f"原始平均RMS: {avg_original:.5f}")
            logger.info(f"处理后平均RMS: {avg_processed:.5f}")

            if avg_original > 0:
                total_reduction = (1 - avg_original / avg_processed) * \
                    100 if avg_processed < avg_original else (
                        1 - avg_processed / avg_original) * 100
                logger.info(f"总体噪音降低: {total_reduction:.1f}%")

            if len(self.stats['noise_reduced_ratio']) > 0:
                avg_reduction = np.mean(self.stats['noise_reduced_ratio'])
                logger.info(f"平均帧降低: {avg_reduction:.1f}%")

        logger.info(f"静音去除: {self.stats['silence_removed']}")
        logger.info(f"噪音压制: {self.stats['noise_suppressed']} 次")
        logger.info(f"语音增强: {self.stats['speech_enhanced']} 次")
        logger.info(f"削波保护: {self.stats['clipped_frames']} 帧")
        logger.info("="*70)


def apply_ultra_noise_reduction(tts_instance, lip_asr=None):
    """应用超强力噪音消除"""
    logger.info("=" * 70)
    logger.info("🔇 应用超强力噪音消除优化")
    logger.info("=" * 70)

    optimizer = UltraNoiseReductionOptimizer(tts_instance, lip_asr)
    optimizer.setup_direct_forwarding()

    # 修补TTS方法
    original_stream_audio = tts_instance.stream_audio

    def patched_stream_audio(audio_array, msg):
        optimizer.optimized_stream_audio(audio_array, msg)

    tts_instance.stream_audio = patched_stream_audio
    tts_instance.optimizer = optimizer

    logger.info("[ULTRA_NOISE] 超强力噪音消除已激活")
    return optimizer
