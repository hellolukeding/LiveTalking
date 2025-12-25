"""
音频处理器 - 终极电音消除方案 v2

核心策略：
1. 高质量重采样（使用scipy polyphase滤波）
2. 跨帧平滑处理（overlap-add with longer crossfade）
3. 抗锯齿滤波（二阶IIR低通）
4. 动态范围压缩
5. 软限幅（soft clipping）
6. DC偏移消除
"""

import numpy as np
from typing import Optional
import threading


class AudioProcessor:
    """高质量音频处理器 - 消除电音/爆音 v2"""
    
    def __init__(
        self,
        target_sample_rate: int = 48000,
        chunk_samples: int = 960,  # 20ms @ 48kHz
        crossfade_samples: int = 96,  # 2ms crossfade @ 48kHz
        enable_lowpass: bool = True,
        lowpass_cutoff: float = 7500.0,  # Hz
        enable_compression: bool = True,
        compression_threshold: float = 0.7,
        compression_ratio: float = 4.0,
    ):
        self.target_sample_rate = target_sample_rate
        self.chunk_samples = chunk_samples
        self.crossfade_samples = crossfade_samples
        self.enable_lowpass = enable_lowpass
        self.lowpass_cutoff = lowpass_cutoff
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold
        self.compression_ratio = compression_ratio
        
        # 状态缓存
        self._prev_tail: Optional[np.ndarray] = None
        self._lowpass_state: np.ndarray = np.zeros(2, dtype=np.float64)  # 二阶滤波器状态
        self._dc_offset: float = 0.0  # DC偏移估计
        self._lock = threading.Lock()
        
        # 预计算crossfade窗口（使用Hann窗，更平滑）
        self._fade_in = 0.5 * (1 - np.cos(np.pi * np.arange(crossfade_samples) / crossfade_samples))
        self._fade_out = 0.5 * (1 + np.cos(np.pi * np.arange(crossfade_samples) / crossfade_samples))
        self._fade_in = self._fade_in.astype(np.float32)
        self._fade_out = self._fade_out.astype(np.float32)
        
        # 预计算二阶Butterworth低通滤波器系数
        self._update_lowpass_coeff()
    
    def _update_lowpass_coeff(self):
        """计算二阶Butterworth低通滤波器系数"""
        import math
        fc = self.lowpass_cutoff
        fs = self.target_sample_rate
        
        # 二阶Butterworth设计
        wc = 2 * math.pi * fc / fs
        wc_warped = 2 * fs * math.tan(wc / 2)
        
        # 归一化
        k = wc_warped / (2 * fs)
        k2 = k * k
        sqrt2 = math.sqrt(2)
        
        # 系数
        norm = 1 / (1 + sqrt2 * k + k2)
        self._b0 = k2 * norm
        self._b1 = 2 * self._b0
        self._b2 = self._b0
        self._a1 = 2 * (k2 - 1) * norm
        self._a2 = (1 - sqrt2 * k + k2) * norm
    
    def resample(self, audio: np.ndarray, orig_sr: int) -> np.ndarray:
        """高质量重采样 - 使用scipy的polyphase滤波"""
        if orig_sr == self.target_sample_rate:
            return audio.astype(np.float32)
        
        try:
            from scipy import signal
            # 使用polyphase重采样，质量更高
            gcd = np.gcd(orig_sr, self.target_sample_rate)
            up = self.target_sample_rate // gcd
            down = orig_sr // gcd
            resampled = signal.resample_poly(audio, up, down)
            return resampled.astype(np.float32)
        except ImportError:
            # 回退到线性插值（比resampy更快，质量足够）
            old_len = len(audio)
            new_len = int(old_len * self.target_sample_rate / orig_sr)
            x_old = np.arange(old_len)
            x_new = np.linspace(0, old_len - 1, new_len)
            return np.interp(x_new, x_old, audio).astype(np.float32)
    
    def remove_dc_offset(self, audio: np.ndarray) -> np.ndarray:
        """移除DC偏移 - 使用高通滤波"""
        # 简单的一阶高通滤波器
        alpha = 0.995  # 截止频率约 ~10Hz @ 48kHz
        output = np.empty_like(audio)
        prev_in = 0.0
        prev_out = self._dc_offset
        
        for i in range(len(audio)):
            output[i] = alpha * (prev_out + audio[i] - prev_in)
            prev_in = audio[i]
            prev_out = output[i]
        
        self._dc_offset = prev_out
        return output
    
    def apply_lowpass(self, audio: np.ndarray) -> np.ndarray:
        """应用二阶Butterworth低通滤波器"""
        if not self.enable_lowpass:
            return audio
        
        output = np.empty_like(audio)
        z1, z2 = self._lowpass_state
        
        for i in range(len(audio)):
            x = float(audio[i])
            y = self._b0 * x + z1
            z1 = self._b1 * x - self._a1 * y + z2
            z2 = self._b2 * x - self._a2 * y
            output[i] = y
        
        self._lowpass_state = np.array([z1, z2], dtype=np.float64)
        return output.astype(np.float32)
    
    def apply_compression(self, audio: np.ndarray) -> np.ndarray:
        """动态范围压缩 - 防止过载"""
        if not self.enable_compression:
            return audio
        
        threshold = self.compression_threshold
        ratio = self.compression_ratio
        
        # 软膝压缩
        abs_audio = np.abs(audio)
        mask = abs_audio > threshold
        
        if np.any(mask):
            # 超过阈值的部分进行压缩
            excess = abs_audio[mask] - threshold
            compressed_excess = excess / ratio
            compressed_level = threshold + compressed_excess
            
            # 保持符号
            output = audio.copy()
            output[mask] = np.sign(audio[mask]) * compressed_level
            return output
        
        return audio
    
    def soft_clip(self, audio: np.ndarray, limit: float = 0.95) -> np.ndarray:
        """软限幅 - 使用tanh平滑限制幅度"""
        max_val = np.max(np.abs(audio))
        if max_val < 0.001:
            return audio
        
        if max_val > limit:
            # 使用tanh进行软限幅
            return np.tanh(audio * 1.5) * limit
        
        return audio
    
    def crossfade_chunks(self, current: np.ndarray) -> np.ndarray:
        """跨帧交叉淡入淡出 - 消除帧边界突变"""
        with self._lock:
            if self._prev_tail is None or len(self._prev_tail) < self.crossfade_samples:
                # 首帧，保存尾部
                if len(current) >= self.crossfade_samples:
                    self._prev_tail = current[-self.crossfade_samples:].copy()
                return current
            
            # 对当前帧头部应用crossfade
            output = current.copy()
            fade_len = min(self.crossfade_samples, len(current), len(self._prev_tail))
            
            if fade_len > 0:
                # 检测跳变
                jump = abs(current[0] - self._prev_tail[-1])
                if jump > 0.01:  # 只在有明显跳变时应用crossfade
                    # 混合前一帧尾部和当前帧头部
                    prev_contribution = self._prev_tail[-fade_len:] * self._fade_out[:fade_len]
                    curr_contribution = current[:fade_len] * self._fade_in[:fade_len]
                    output[:fade_len] = prev_contribution + curr_contribution
            
            # 保存当前帧尾部
            if len(current) >= self.crossfade_samples:
                self._prev_tail = current[-self.crossfade_samples:].copy()
            
            return output
    
    def process_chunk(self, audio: np.ndarray, source_sr: int = None) -> np.ndarray:
        """
        完整的音频处理管道
        
        Args:
            audio: 输入音频数据 (float32 或 int16)
            source_sr: 源采样率，如果与目标不同则重采样
        
        Returns:
            处理后的int16音频数据
        """
        # 1. 转换为float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32767.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        # 2. 重采样（如果需要）
        if source_sr and source_sr != self.target_sample_rate:
            audio = self.resample(audio, source_sr)
        
        # 3. 移除DC偏移
        audio = self.remove_dc_offset(audio)
        
        # 4. 低通滤波
        audio = self.apply_lowpass(audio)
        
        # 5. 跨帧平滑
        audio = self.crossfade_chunks(audio)
        
        # 6. 动态压缩
        audio = self.apply_compression(audio)
        
        # 7. 软限幅
        audio = self.soft_clip(audio)
        
        # 8. 转换为int16
        output = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        
        return output
    
    def reset(self):
        """重置处理器状态"""
        with self._lock:
            self._prev_tail = None
            self._lowpass_state = np.zeros(2, dtype=np.float64)
            self._dc_offset = 0.0


class StreamingAudioBuffer:
    """流式音频缓冲器 - 处理不定长输入，输出固定长度chunk"""
    
    def __init__(
        self,
        processor: AudioProcessor,
        chunk_samples: int = 320,
        max_buffer_samples: int = 16000,  # 1秒缓冲
    ):
        self.processor = processor
        self.chunk_samples = chunk_samples
        self.max_buffer_samples = max_buffer_samples
        
        self._buffer = np.array([], dtype=np.float32)
        self._lock = threading.Lock()
    
    def add_audio(self, audio: np.ndarray, source_sr: int = None) -> list[np.ndarray]:
        """
        添加音频数据，返回可用的完整chunk列表
        
        Args:
            audio: 输入音频
            source_sr: 源采样率
        
        Returns:
            处理后的int16 chunk列表
        """
        # 转换为float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32767.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        # 重采样
        if source_sr and source_sr != self.processor.target_sample_rate:
            audio = self.processor.resample(audio, source_sr)
        
        with self._lock:
            # 添加到缓冲区
            self._buffer = np.concatenate([self._buffer, audio])
            
            # 防止缓冲区过大
            if len(self._buffer) > self.max_buffer_samples:
                self._buffer = self._buffer[-self.max_buffer_samples:]
            
            # 提取完整的chunk
            chunks = []
            while len(self._buffer) >= self.chunk_samples:
                chunk = self._buffer[:self.chunk_samples].copy()
                self._buffer = self._buffer[self.chunk_samples:]
                
                # 处理chunk
                processed = self.processor.process_chunk(chunk)
                chunks.append(processed)
            
            return chunks
    
    def flush(self) -> Optional[np.ndarray]:
        """刷新缓冲区，返回剩余数据（补零到chunk长度）"""
        with self._lock:
            if len(self._buffer) == 0:
                return None
            
            # 补零
            padded = np.zeros(self.chunk_samples, dtype=np.float32)
            padded[:len(self._buffer)] = self._buffer
            self._buffer = np.array([], dtype=np.float32)
            
            return self.processor.process_chunk(padded)
    
    def reset(self):
        """重置缓冲器"""
        with self._lock:
            self._buffer = np.array([], dtype=np.float32)
        self.processor.reset()
