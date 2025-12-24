#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度噪音消除优化器
专门解决DoubaoTTS噪音过大问题
"""

import queue
import threading
import time
from typing import Dict, Optional

import numpy as np

from logger import logger


class DeepNoiseReductionOptimizer:
    """深度噪音消除优化器"""

    def __init__(self, tts_instance, lip_asr=None):
        self.tts = tts_instance
        self.lip_asr = lip_asr

        # 🔧 超级噪音消除配置
        self.noise_config = {
            # 静音检测
            'silence_threshold': 0.001,  # 更严格的静音阈值

            # 噪音门限
            'noise_threshold': 0.002,    # 噪音阈值
            'noise_reduction_factor': 0.05,  # 噪音压制倍数

            # 高频噪音消除
            'high_freq_cutoff': 4000,    # 高频截止频率 (16kHz采样率)
            'high_freq_reduction': 0.3,  # 高频衰减

            # 动态范围压缩
            'dynamic_range_threshold': 0.05,  # 动态范围阈值
            'compression_ratio': 2.0,         # 压缩比

            # 增益控制（更保守）
            'max_gain': 1.2,             # 最大增益（之前是1.5-2.0）
            'target_level': 0.15,        # 目标音量水平（之前是0.3）

            # 削波保护
            'clip_limit': 0.85,          # 削波限制（更严格）

            # 多频段处理
            'enable_multiband': True,    # 启用多频段处理
            'num_bands': 5,              # 频段数量

            # 语音增强
            'speech_enhancement': True,  # 语音增强
            'speech_threshold': 0.01,    # 语音检测阈值

            # 降噪强度
            'aggressiveness': 3,         # 降噪强度 (1-3)
        }

        # 统计信息
        self.stats = {
            'total_frames': 0,
            'noise_frames': 0,
            'silence_frames': 0,
            'speech_frames': 0,
            'clipped_frames': 0,
            'gain_applied': 0,
            'noise_reduced': 0,
            'high_freq_filtered': 0,
            'dynamic_compressed': 0,
            'original_rms': [],
            'processed_rms': [],
            'noise_level': [],
        }

        # 缓冲区
        self.audio_buffer = queue.Queue(maxsize=100)
        self.processing_lock = threading.Lock()

        # 状态
        self.lip_asr_ready = False
        self.audio_track_ready = False

        logger.info("[DEEP_NOISE] 深度噪音消除优化器已初始化")

    def setup_direct_forwarding(self):
        """设置直接转发路径"""
        logger.info("[DEEP_NOISE] 设置转发路径")

        # 检查唇形驱动
        if hasattr(self.tts, 'parent') and hasattr(self.tts.parent, 'lip_asr'):
            self.lip_asr = self.tts.parent.lip_asr
            if hasattr(self.lip_asr, 'feat_queue') and hasattr(self.lip_asr, 'output_queue'):
                self.lip_asr_ready = True
                logger.info("[DEEP_NOISE] LipASR就绪")

        # 检查音频轨道
        if hasattr(self.tts, 'audio_track') and self.tts.audio_track:
            self.audio_track_ready = True
            logger.info("[DEEP_NOISE] 音频轨道就绪")

        return self.lip_asr_ready

    def analyze_audio_quality(self, audio_chunk: np.ndarray) -> Dict:
        """深度音频质量分析"""
        if len(audio_chunk) == 0:
            return {'peak': 0, 'rms': 0, 'is_silence': True, 'noise_level': 0, 'speech_energy': 0}

        peak = np.max(np.abs(audio_chunk))
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        # 静音检测
        is_silence = peak < self.noise_config['silence_threshold']

        # 噪音水平计算（使用统计方法）
        if len(audio_chunk) > 0:
            # 计算噪音水平（低能量部分）
            threshold = np.percentile(np.abs(audio_chunk), 25)
            noise_mask = np.abs(audio_chunk) < threshold
            noise_level = np.sqrt(
                np.mean(audio_chunk[noise_mask] ** 2)) if np.sum(noise_mask) > 0 else 0

            # 语音能量（高能量部分）
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
            'snr': speech_energy / (noise_level + 1e-10),  # 信噪比
        }

    def apply_noise_reduction(self, audio_chunk: np.ndarray) -> np.ndarray:
        """应用多重噪音消除技术"""
        processed = audio_chunk.copy()

        # 0. 输入保护 - 防止过载
        if np.max(np.abs(processed)) > 1.0:
            processed = np.clip(processed, -0.95, 0.95)

        # 1. 静音检测和去除
        peak = np.max(np.abs(processed))
        if peak < self.noise_config['silence_threshold']:
            # 完全静音，返回零
            return np.zeros_like(processed) * 0.01

        # 2. 噪音门限消除（硬阈值）
        noise_mask = np.abs(processed) < self.noise_config['noise_threshold']
        processed[noise_mask] = processed[noise_mask] * \
            self.noise_config['noise_reduction_factor']

        # 3. 多频段处理（如果启用）
        if self.noise_config['enable_multiband']:
            processed = self._multiband_processing(processed)

        # 4. 高频噪音消除
        processed = self._high_freq_reduction(processed)

        # 5. 动态范围压缩
        processed = self._dynamic_range_compression(processed)

        # 6. 语音增强（如果启用）
        if self.noise_config['speech_enhancement']:
            processed = self._speech_enhancement(processed)

        # 7. 保守增益控制（严格限制）
        rms = np.sqrt(np.mean(processed ** 2))
        if rms > 0:
            target_rms = self.noise_config['target_level']
            current_gain = target_rms / rms
            # 限制最大增益，避免放大噪音
            current_gain = min(current_gain, self.noise_config['max_gain'])
            processed = processed * current_gain

        # 8. 削波保护（严格）
        processed = np.clip(
            processed, -self.noise_config['clip_limit'], self.noise_config['clip_limit'])

        # 9. 软限幅（防止硬削波）
        soft_clip_threshold = self.noise_config['clip_limit'] * 0.9
        mask = np.abs(processed) > soft_clip_threshold
        if np.any(mask):
            # 使用软削波函数
            x = processed[mask]
            processed[mask] = np.sign(
                x) * (1 - np.exp(-np.abs(x) / soft_clip_threshold)) * soft_clip_threshold

        return processed

    def _multiband_processing(self, audio_chunk: np.ndarray) -> np.ndarray:
        """多频段处理"""
        # 使用FFT进行频域处理
        fft = np.fft.rfft(audio_chunk)
        freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

        # 创建频段掩码
        bands = np.linspace(0, 8000, self.noise_config['num_bands'] + 1)

        for i in range(len(bands) - 1):
            band_mask = (freqs >= bands[i]) & (freqs < bands[i+1])

            # 对高频段进行更强的降噪
            if bands[i] > 4000:
                fft[band_mask] *= 0.7  # 高频衰减

            # 对低频段保持语音
            elif bands[i] < 500:
                fft[band_mask] *= 1.0  # 保持

            # 中频段适度处理
            else:
                fft[band_mask] *= 0.9

        # 逆FFT
        processed = np.fft.irfft(fft, len(audio_chunk))

        # 确保长度一致
        if len(processed) != len(audio_chunk):
            processed = processed[:len(audio_chunk)]

        return processed

    def _high_freq_reduction(self, audio_chunk: np.ndarray) -> np.ndarray:
        """高频噪音消除"""
        # 使用简单的低通滤波器
        cutoff = self.noise_config['high_freq_cutoff']
        sample_rate = 16000

        # 计算滤波器系数
        nyquist = sample_rate / 2
        cutoff_norm = cutoff / nyquist

        # 简单的移动平均滤波器（低通）
        window_size = int(sample_rate / cutoff)
        if window_size % 2 == 0:
            window_size += 1

        if window_size > 1:
            # 使用加权移动平均
            kernel = np.ones(window_size) / window_size
            # 使滤波器更平滑
            processed = np.convolve(audio_chunk, kernel, mode='same')

            # 混合原始信号和滤波信号
            alpha = self.noise_config['high_freq_reduction']
            processed = alpha * processed + (1 - alpha) * audio_chunk
        else:
            processed = audio_chunk

        return processed

    def _dynamic_range_compression(self, audio_chunk: np.ndarray) -> np.ndarray:
        """动态范围压缩"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms < self.noise_config['dynamic_range_threshold']:
            # 低电平信号，压缩动态范围
            threshold = self.noise_config['dynamic_range_threshold']
            ratio = self.noise_config['compression_ratio']

            # 计算压缩增益
            gain = np.ones_like(audio_chunk)

            # 对低电平部分进行压缩
            low_mask = np.abs(audio_chunk) < threshold
            if np.any(low_mask):
                # 平滑压缩
                gain[low_mask] = 1.0 + (ratio - 1.0) * (threshold -
                                                        np.abs(audio_chunk[low_mask])) / threshold
                gain[low_mask] = np.clip(gain[low_mask], 1.0, ratio)

            processed = audio_chunk * gain
            self.stats['dynamic_compressed'] += 1
        else:
            processed = audio_chunk

        return processed

    def _speech_enhancement(self, audio_chunk: np.ndarray) -> np.ndarray:
        """语音增强"""
        # 计算语音存在概率
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms > self.noise_config['speech_threshold']:
            # 检测到语音，进行增强
            # 使用频谱提升
            fft = np.fft.rfft(audio_chunk)
            freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

            # 提升语音频段 (300-3400Hz)
            speech_mask = (freqs >= 300) & (freqs <= 3400)
            fft[speech_mask] *= 1.2  # 提升语音

            # 抑制非语音频段
            non_speech_mask = ~speech_mask
            fft[non_speech_mask] *= 0.8  # 抑制

            processed = np.fft.irfft(fft, len(audio_chunk))
            if len(processed) != len(audio_chunk):
                processed = processed[:len(audio_chunk)]

            # 混合原始信号
            processed = 0.7 * processed + 0.3 * audio_chunk
        else:
            processed = audio_chunk

        return processed

    def send_to_webrtc(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """发送到WebRTC"""
        if not (self.tts.audio_track and self.tts.loop):
            return False

        try:
            # 转换格式
            frame = (audio_chunk * 32767).astype(np.int16).reshape(1, -1)

            from av import AudioFrame
            audio_frame = AudioFrame.from_ndarray(
                frame, layout='mono', format='s16')
            audio_frame.sample_rate = 16000

            # 发送
            self.tts.audio_track._queue.put_nowait((audio_frame, eventpoint))
            return True

        except queue.Full:
            logger.warning("[DEEP_NOISE] WebRTC队列满")
            return False
        except Exception as e:
            logger.error(f"[DEEP_NOISE] WebRTC发送失败: {e}")
            return False

    def send_to_lip_asr(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """发送到唇形驱动"""
        if not (self.lip_asr and self.lip_asr_ready):
            return False

        try:
            self.lip_asr.put_audio_frame(audio_chunk, eventpoint)
            return True
        except Exception as e:
            logger.error(f"[DEEP_NOISE] LipASR发送失败: {e}")
            return False

    def process_audio_frame(self, audio_chunk: np.ndarray, eventpoint: Dict):
        """处理单个音频帧"""
        self.stats['total_frames'] += 1

        # 分析原始音频
        original_quality = self.analyze_audio_quality(audio_chunk)
        self.stats['original_rms'].append(original_quality['rms'])
        self.stats['noise_level'].append(original_quality['noise_level'])

        # 应用噪音消除
        processed_chunk = self.apply_noise_reduction(audio_chunk)

        # 分析处理后音频
        processed_quality = self.analyze_audio_quality(processed_chunk)
        self.stats['processed_rms'].append(processed_quality['rms'])

        # 统计
        if original_quality['is_silence']:
            self.stats['silence_frames'] += 1
        elif original_quality['noise_level'] > original_quality['speech_energy']:
            self.stats['noise_frames'] += 1
        else:
            self.stats['speech_frames'] += 1

        if np.max(np.abs(processed_chunk)) > 0.85:
            self.stats['clipped_frames'] += 1

        if processed_quality['rms'] > original_quality['rms']:
            self.stats['gain_applied'] += 1

        if processed_quality['noise_level'] < original_quality['noise_level'] * 0.5:
            self.stats['noise_reduced'] += 1

        # 双路发送
        webrtc_ok = self.send_to_webrtc(processed_chunk, eventpoint)
        lip_ok = self.send_to_lip_asr(processed_chunk, eventpoint)

        return webrtc_ok or lip_ok

    def optimized_stream_audio(self, audio_array: np.ndarray, msg: tuple):
        """优化的音频流处理"""
        text, textevent = msg

        logger.info(f"[DEEP_NOISE] 开始处理音频流，长度: {len(audio_array)}")

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

            # 短暂延迟
            time.sleep(0.01)

        # 输出统计
        self._log_statistics(total_frames, success_frames)

        return success_frames > 0

    def _log_statistics(self, total_frames, success_frames):
        """输出详细统计"""
        logger.info("="*60)
        logger.info("[DEEP_NOISE] 处理完成统计")
        logger.info("="*60)
        logger.info(f"总帧数: {total_frames}, 成功: {success_frames}")

        if len(self.stats['original_rms']) > 0:
            avg_original = np.mean(self.stats['original_rms'])
            avg_processed = np.mean(self.stats['processed_rms'])
            avg_noise = np.mean(self.stats['noise_level'])

            logger.info(f"原始RMS: {avg_original:.4f}")
            logger.info(f"处理后RMS: {avg_processed:.4f}")
            logger.info(f"平均噪音: {avg_noise:.4f}")
            logger.info(f"噪音降低: {(1 - avg_processed/avg_original)*100:.1f}%")

        logger.info(f"静音帧: {self.stats['silence_frames']}")
        logger.info(f"噪音帧: {self.stats['noise_frames']}")
        logger.info(f"语音帧: {self.stats['speech_frames']}")
        logger.info(f"削波帧: {self.stats['clipped_frames']}")
        logger.info(f"增益应用: {self.stats['gain_applied']}")
        logger.info(f"噪音消除: {self.stats['noise_reduced']}")
        logger.info("="*60)

    def get_status_report(self) -> Dict:
        """获取状态报告"""
        return {
            'lip_asr_ready': self.lip_asr_ready,
            'audio_track_ready': self.audio_track_ready,
            'stats': self.stats.copy(),
            'config': self.noise_config,
            'buffer_size': self.audio_buffer.qsize(),
        }


def apply_deep_noise_reduction(tts_instance, lip_asr=None):
    """应用深度噪音消除"""
    logger.info("=" * 70)
    logger.info("🔇 应用深度噪音消除优化")
    logger.info("=" * 70)

    optimizer = DeepNoiseReductionOptimizer(tts_instance, lip_asr)

    # 1. 设置转发路径
    optimizer.setup_direct_forwarding()

    # 2. 修补TTS方法
    original_stream_audio = tts_instance.stream_audio

    def patched_stream_audio(audio_array, msg):
        optimizer.optimized_stream_audio(audio_array, msg)

    tts_instance.stream_audio = patched_stream_audio

    # 3. 保存引用
    t
