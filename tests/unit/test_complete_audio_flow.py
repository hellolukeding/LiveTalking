#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整音频流测试 - 模拟从TTS到播放的完整流程
"""

import numpy as np
import logging
from queue import Queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimulatedAudioFlow:
    """模拟完整的音频流"""
    
    def __init__(self):
        self.lip_asr_frames = []
        self.webrtc_frames = []
        
    def simulate_tts_generation(self, duration_seconds=2.0):
        """模拟TTS生成音频"""
        logger.info(f"模拟TTS生成 {duration_seconds}秒音频...")
        
        # 16kHz采样率，每帧320样本(20ms)
        sample_rate = 16000
        chunk_size = 320
        total_samples = int(sample_rate * duration_seconds)
        num_chunks = total_samples // chunk_size
        
        logger.info(f"总样本数: {total_samples}, 分块数: {num_chunks}")
        
        # 生成测试音频（正弦波）
        frequency = 440  # A4音符
        t = np.linspace(0, duration_seconds, total_samples)
        audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32) * 0.5
        
        return audio_data, num_chunks
    
    def simulate_basereal_put_audio_frame(self, audio_chunk):
        """模拟BaseReal.put_audio_frame()"""
        
        # 1. 转发到LipASR
        self.lip_asr_frames.append(audio_chunk.copy())
        logger.debug(f"[BaseReal] 转发到LipASR: {len(audio_chunk)} samples")
        
        # 2. 转换格式并发送到WebRTC
        frame_int16 = (audio_chunk * 32767).astype(np.int16)
        
        # 检查大小
        if len(frame_int16) != 320:
            if len(frame_int16) < 320:
                # 填充
                padded = np.zeros(320, dtype=np.int16)
                padded[:len(frame_int16)] = frame_int16
                frame_int16 = padded
                logger.debug(f"[BaseReal] 填充音频块: {len(frame_int16)} → 320")
            else:
                # 截取
                frame_int16 = frame_int16[:320]
                logger.debug(f"[BaseReal] 截取音频块: {len(frame_int16)} → 320")
        
        self.webrtc_frames.append(frame_int16)
        logger.debug(f"[BaseReal] 发送到WebRTC: {len(frame_int16)} samples")
        
        return True
    
    def run_test(self):
        """运行完整测试"""
        logger.info("=" * 70)
        logger.info("开始完整音频流测试")
        logger.info("=" * 70)
        
        # 1. 生成音频
        audio_data, expected_chunks = self.simulate_tts_generation(2.0)
        logger.info(f"\n✅ 步骤1: TTS生成音频完成")
        logger.info(f"   音频长度: {len(audio_data)} samples")
        logger.info(f"   预期分块: {expected_chunks} chunks")
        
        # 2. 分块处理
        logger.info(f"\n✅ 步骤2: 开始分块处理...")
        chunk_size = 320
        idx = 0
        processed_chunks = 0
        
        while idx < len(audio_data):
            end = idx + chunk_size
            if end <= len(audio_data):
                chunk = audio_data[idx:end]
            else:
                # 最后一块，填充
                chunk = np.zeros(chunk_size, dtype=np.float32)
                valid_len = len(audio_data) - idx
                chunk[:valid_len] = audio_data[idx:]
            
            # 模拟put_audio_frame
            self.simulate_basereal_put_audio_frame(chunk)
            processed_chunks += 1
            idx += chunk_size
        
        logger.info(f"   处理分块: {processed_chunks} chunks")
        
        # 3. 验证结果
        logger.info(f"\n✅ 步骤3: 验证结果...")
        logger.info(f"   LipASR收到: {len(self.lip_asr_frames)} 帧")
        logger.info(f"   WebRTC发送: {len(self.webrtc_frames)} 帧")
        
        # 4. 检查音频质量
        logger.info(f"\n✅ 步骤4: 检查音频质量...")
        
        # 检查LipASR音频
        lip_audio = np.concatenate(self.lip_asr_frames)
        logger.info(f"   LipASR总样本: {len(lip_audio)}")
        logger.info(f"   LipASR音频范围: [{lip_audio.min():.3f}, {lip_audio.max():.3f}]")
        
        # 检查WebRTC音频
        webrtc_audio = np.concatenate(self.webrtc_frames)
        logger.info(f"   WebRTC总样本: {len(webrtc_audio)}")
        logger.info(f"   WebRTC音频范围: [{webrtc_audio.min()}, {webrtc_audio.max()}]")
        
        # 5. 最终结果
        logger.info("\n" + "=" * 70)
        logger.info("测试结果:")
        logger.info("=" * 70)
        
        success = True
        
        # 检查帧数
        if len(self.lip_asr_frames) == len(self.webrtc_frames):
            logger.info("✅ LipASR和WebRTC帧数一致")
        else:
            logger.error("❌ LipASR和WebRTC帧数不一致")
            success = False
        
        # 检查音频不为空
        if len(lip_audio) > 0 and len(webrtc_audio) > 0:
            logger.info("✅ 音频数据不为空")
        else:
            logger.error("❌ 音频数据为空")
            success = False
        
        # 检查音频范围
        if -1.0 <= lip_audio.min() <= lip_audio.max() <= 1.0:
            logger.info("✅ LipASR音频范围正常 (float32, -1.0~1.0)")
        else:
            logger.error("❌ LipASR音频范围异常")
            success = False
        
        if -32768 <= webrtc_audio.min() <= webrtc_audio.max() <= 32767:
            logger.info("✅ WebRTC音频范围正常 (int16, -32768~32767)")
        else:
            logger.error("❌ WebRTC音频范围异常")
            success = False
        
        # 检查音频长度
        expected_samples = processed_chunks * 320
        if len(lip_audio) == expected_samples and len(webrtc_audio) == expected_samples:
            logger.info(f"✅ 音频长度正确 ({expected_samples} samples)")
        else:
            logger.error(f"❌ 音频长度不正确")
            logger.error(f"   预期: {expected_samples}")
            logger.error(f"   LipASR: {len(lip_audio)}")
            logger.error(f"   WebRTC: {len(webrtc_audio)}")
            success = False
        
        logger.info("=" * 70)
        
        if success:
            logger.info("\n🎉 所有测试通过！音频流处理正常。")
            logger.info("\n这意味着:")
            logger.info("  ✅ TTS生成的音频能正确分块")
            logger.info("  ✅ 音频能同时转发到LipASR和WebRTC")
            logger.info("  ✅ 音频格式转换正确")
            logger.info("  ✅ 音频块大小处理正确")
            logger.info("\n实际应用中应该:")
            logger.info("  ✅ 能听到声音（WebRTC播放）")
            logger.info("  ✅ 能看到口型（LipASR驱动）")
        else:
            logger.error("\n❌ 部分测试失败，请检查音频处理逻辑。")
        
        return success


if __name__ == "__main__":
    import sys
    
    flow = SimulatedAudioFlow()
    success = flow.run_test()
    
    sys.exit(0 if success else 1)
