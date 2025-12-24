#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试音频修复 - 验证DoubaoTTS音频播放和驱动
"""

import os
import sys
import time
import numpy as np
from queue import Queue
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockLipASR:
    """模拟LipASR"""
    def __init__(self):
        self.audio_frames = []
        self.queue = Queue()
        
    def put_audio_frame(self, audio_chunk, datainfo):
        self.audio_frames.append((audio_chunk.copy(), datainfo))
        logger.info(f"[LipASR] 收到音频帧: {len(audio_chunk)} samples, 总计: {len(self.audio_frames)}")


class MockAudioTrack:
    """模拟WebRTC音频轨道"""
    def __init__(self):
        self._queue = MockQueue()
        self.frames_sent = 0
        
    class MockQueue:
        def __init__(self):
            self.items = []
            self._loop = MockLoop()
            
        def qsize(self):
            return len(self.items)
            
        def put_nowait(self, item):
            self.items.append(item)
            
    class MockLoop:
        def is_running(self):
            return True
            
        def call_soon_threadsafe(self, func, *args):
            func(*args)


class MockBaseReal:
    """模拟BaseReal"""
    def __init__(self):
        self.audio_frames = []
        self.lip_asr = MockLipASR()
        self.audio_track = MockAudioTrack()
        self.loop = self.audio_track._queue._loop
        self._pending_audio = []
        import threading
        self._pending_audio_lock = threading.Lock()
        
    def put_audio_frame(self, audio_chunk, datainfo={}):
        """模拟basereal的put_audio_frame"""
        logger.info(f"[BaseReal] put_audio_frame: {len(audio_chunk)} samples")
        
        # 转发给LipASR
        if hasattr(self, 'lip_asr'):
            self.lip_asr.put_audio_frame(audio_chunk, datainfo)
            logger.info("[BaseReal] 音频已转发到LipASR")
        
        # 转发给WebRTC
        try:
            from av import AudioFrame
            frame = (audio_chunk * 32767).astype(np.int16)
            frame_2d = frame.reshape(1, -1)
            audio_frame = AudioFrame.from_ndarray(frame_2d, layout='mono', format='s16')
            audio_frame.sample_rate = 16000
            
            if self.audio_track and self.audio_track._queue:
                self.audio_track._queue.put_nowait((audio_frame, datainfo))
                self.audio_track.frames_sent += 1
                logger.info(f"[BaseReal] 音频已发送到WebRTC, 总计: {self.audio_track.frames_sent}")
        except Exception as e:
            logger.error(f"[BaseReal] WebRTC发送失败: {e}")


def test_doubao_tts():
    """测试DoubaoTTS音频流"""
    logger.info("=" * 70)
    logger.info("测试DoubaoTTS音频播放和驱动")
    logger.info("=" * 70)
    
    # 检查环境变量
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID", "BV001_STREAMING")
    
    if not appid or not token:
        logger.error("❌ 缺少环境变量: DOUBAO_APPID, DOUBAO_TOKEN")
        return False
    
    logger.info(f"✅ 环境变量配置正确")
    logger.info(f"   APPID: {appid[:10]}...")
    logger.info(f"   Voice ID: {voice_id}")
    
    # 创建模拟对象
    try:
        # 创建opt对象
        class MockOpt:
            def __init__(self):
                self.fps = 50  # 20ms per frame
                self.REF_FILE = voice_id
                self.batch_size = 4
        
        opt = MockOpt()
        parent = MockBaseReal()
        
        # 导入DoubaoTTS
        from ttsreal import DoubaoTTS
        
        logger.info("✅ DoubaoTTS导入成功")
        
        # 创建TTS实例
        tts = DoubaoTTS(opt, parent)
        logger.info("✅ DoubaoTTS实例创建成功")
        
        # 测试文本
        test_text = "你好，这是一个测试。"
        logger.info(f"\n测试文本: {test_text}")
        
        # 发送TTS请求
        logger.info("\n开始TTS处理...")
        tts.txt_to_audio((test_text, {'text': test_text}))
        
        # 检查结果
        logger.info("\n" + "=" * 70)
        logger.info("测试结果:")
        logger.info("=" * 70)
        
        lip_frames = len(parent.lip_asr.audio_frames)
        webrtc_frames = parent.audio_track.frames_sent
        
        logger.info(f"LipASR收到音频帧: {lip_frames}")
        logger.info(f"WebRTC发送音频帧: {webrtc_frames}")
        
        if lip_frames > 0 and webrtc_frames > 0:
            logger.info("\n✅ 测试通过!")
            logger.info("   - 音频正确转发到LipASR (口型驱动)")
            logger.info("   - 音频正确发送到WebRTC (声音播放)")
            return True
        else:
            logger.error("\n❌ 测试失败!")
            if lip_frames == 0:
                logger.error("   - LipASR未收到音频帧 (无口型驱动)")
            if webrtc_frames == 0:
                logger.error("   - WebRTC未收到音频帧 (无声音)")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = test_doubao_tts()
    sys.exit(0 if success else 1)
