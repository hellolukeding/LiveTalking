#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终极噪音消除器
在音频处理的每个阶段都应用噪音消除
"""

import numpy as np

from logger import logger


class FinalNoiseEliminator:
    """终极噪音消除器 - 在basereal.py中使用"""

    def __init__(self):
        # 终极配置 - 针对"仍然噪音过大"的最终解决方案
        self.config = {
            # 第一层：激进噪音门限（在原始音频上）
            'noise_threshold': 0.0008,      # 极严格
            'noise_reduction_factor': 0.005,  # 压制99.5%噪音

            # 第二层：高频消除（在转换前）
            'high_freq_cutoff': 2500,       # 2.5kHz截止（更激进）
            'high_freq_reduction': 0.05,    # 高频压制95%

            # 第三层：多频段处理（8个频段）
            'band_reduction': [
                1.0,   # 0-200Hz (保留)
                0.9,   # 200-500Hz (保留90%)
                0.6,   # 500-1000Hz (压制40%)
                0.3,   # 1000-2000Hz (压制70%)
                0.15,  # 2000-2500Hz (压制85%)
                0.08,  # 2500-3000Hz (压制92%)
                0.03,  # 3000-4000Hz (压制97%)
                0.01,  # 4000-8000Hz (压制99%)
            ],

            # 第四层：语音频段保护
            'speech_band': [300, 2500],     # 语音频段
            'speech_boost': 1.3,            # 语音提升

            # 第五层：动态范围压缩
            'compression_threshold': 0.015,  # 低电平压缩
            'compression_ratio': 4.0,       # 4:1压缩比

            # 第六层：增益控制（最终）
            'target_level': 0.10,           # 目标音量
            'max_gain': 0.8,                # 最大增益0.8倍（不放大）

            # 第七层：严格削波保护
            'clip_limit': 0.70,             # 严格削波
            'soft_clip': True,              # 软削波

            # 第八层：静音检测
            'silence_threshold': 0.0003,    # 超严格静音

            # 第九层：噪音学习
            'noise_learning': True,
            'noise_history_size': 30,
        }

        # 噪音历史
        self.noise_history = []

        logger.info("[FINAL_NOISE] 终极噪音消除器已初始化")

    def apply_final_elimination(self, audio_chunk: np.ndarray) -> np.ndarray:
        """应用终极噪音消除"""
        processed = audio_chunk.copy()

        # 0. 输入保护
        if np.max(np.abs(processed)) > 1.0:
            processed = np.clip(processed, -0.95, 0.95)

        # 1. 静音检测和去除
        peak = np.max(np.abs(processed))
        if peak < self.config['silence_threshold']:
            return np.zeros_like(processed) * 0.002  # 几乎完全静音

        # 2. 激进噪音门限
        noise_mask = np.abs(processed) < self.config['noise_threshold']
        processed[noise_mask] = processed[noise_mask] * \
            self.config['noise_reduction_factor']

        # 3. 多频段处理
        processed = self._ultra_multiband(processed)

        # 4. 高频强力消除
        processed = self._ultra_high_freq(processed)

        # 5. 语音频段保护和增强
        processed = self._speech_enhancement(processed)

        # 6. 动态范围压缩
        processed = self._dynamic_compression(processed)

        # 7. 最终增益控制
        rms = np.sqrt(np.mean(processed ** 2))
        if rms > 0:
            target_rms = self.config['target_level']
            current_gain = target_rms / rms
            current_gain = min(current_gain, self.config['max_gain'])
            processed = processed * current_gain

        # 8. 严格削波保护
        processed = np.clip(
            processed, -self.config['clip_limit'], self.config['clip_limit'])

        # 9. 软削波
        if self.config['soft_clip']:
            threshold = self.config['clip_limit'] * 0.80
            mask = np.abs(processed) > threshold
            if np.any(mask):
                x = processed[mask]
                processed[mask] = np.sign(
                    x) * (1 - np.exp(-np.abs(x) / threshold)) * threshold

        return processed

    def _ultra_multiband(self, audio_chunk):
        """超强力多频段处理"""
        fft = np.fft.rfft(audio_chunk)
        freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

        bands = [0, 200, 500, 1000, 2000, 2500, 3000, 4000, 8000]

        for i in range(len(bands) - 1):
            band_mask = (freqs >= bands[i]) & (freqs < bands[i+1])
            reduction = self.config['band_reduction'][i]
            fft[band_mask] *= reduction

        processed = np.fft.irfft(fft, len(audio_chunk))
        if len(processed) != len(audio_chunk):
            processed = processed[:len(audio_chunk)]

        return processed

    def _ultra_high_freq(self, audio_chunk):
        """超强力高频消除"""
        cutoff = self.config['high_freq_cutoff']
        sample_rate = 16000

        window_size = int(sample_rate / cutoff) * 3  # 更大窗口
        if window_size % 2 == 0:
            window_size += 1

        if window_size > 3:
            kernel = np.sinc(
                np.arange(-window_size//2, window_size//2+1) * cutoff / sample_rate)
            kernel = kernel / np.sum(kernel)
            processed = np.convolve(audio_chunk, kernel, mode='same')

            alpha = self.config['high_freq_reduction']
            processed = alpha * processed + (1 - alpha) * audio_chunk
        else:
            processed = audio_chunk

        return processed

    def _speech_enhancement(self, audio_chunk):
        """语音频段保护和增强"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms > 0.003:  # 检测到语音
            fft = np.fft.rfft(audio_chunk)
            freqs = np.fft.rfftfreq(len(audio_chunk), 1/16000)

            speech_band = self.config['speech_band']
            speech_mask = (freqs >= speech_band[0]) & (freqs <= speech_band[1])

            if np.any(speech_mask):
                # 语音频段增强
                fft[speech_mask] *= self.config['speech_boost']

                # 非语音频段强力压制
                non_speech_mask = ~speech_mask
                fft[non_speech_mask] *= 0.2  # 压制80%

                processed = np.fft.irfft(fft, len(audio_chunk))
                if len(processed) != len(audio_chunk):
                    processed = processed[:len(audio_chunk)]

                processed = 0.85 * processed + 0.15 * audio_chunk
                return processed

        return audio_chunk

    def _dynamic_compression(self, audio_chunk):
        """强力动态范围压缩"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))

        if rms < self.config['compression_threshold']:
            threshold = self.config['compression_threshold']
            ratio = self.config['compression_ratio']

            gain = np.ones_like(audio_chunk)
            low_mask = np.abs(audio_chunk) < threshold

            if np.any(low_mask):
                gain[low_mask] = 1.0 + (ratio - 1.0) * (threshold -
                                                        np.abs(audio_chunk[low_mask])) / threshold
                gain[low_mask] = np.clip(gain[low_mask], 1.0, ratio)

            return audio_chunk * gain

        return audio_chunk

    def process_for_webrtc(self, audio_chunk):
        """为WebRTC处理音频 - 在basereal.py中调用"""
        # 应用终极噪音消除
        processed = self.apply_final_elimination(audio_chunk)

        # 转换为16-bit
        processed_int16 = (processed * 32767).astype(np.int16)

        return processed_int16

    def get_stats(self):
        """获取统计信息"""
        return {
            'noise_history_size': len(self.noise_history),
            'config': self.config
        }


def integrate_into_basereal(basereal_instance):
    """将终极噪音消除器集成到basereal.py"""
    logger.info("=" * 70)
    logger.info("🔇 集成终极噪音消除器到basereal.py")
    logger.info("=" * 70)

    # 创建消除器
    eliminator = FinalNoiseEliminator()

    # 保存原始方法
    original_put_audio_frame = basereal_instance.put_audio_frame

    def patched_put_audio_frame(audio_chunk, datainfo={}):
        """应用终极噪音消除的put_audio_frame"""
        logger.debug(f"[FINAL_NOISE] 处理音频块: {audio_chunk.shape}")

        # 应用噪音消除
        processed_chunk = eliminator.apply_final_elimination(audio_chunk)

        # 继续原始流程
        return original_put_audio_frame(processed_chunk, datainfo)

    # 替换方法
    basereal_instance.put_audio_frame = patched_put_audio_frame
    basereal_instance.final_eliminator = eliminator

    logger.info("[FINAL_NOISE] 终极噪音消除器集成完成")
    return eliminator
