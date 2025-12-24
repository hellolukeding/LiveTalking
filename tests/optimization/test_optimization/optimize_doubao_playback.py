#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DoubaoTTS 播放优化 - 解决消息丢失和唇形驱动失效问题

问题分析：
1. 消息丢失：长对话经常性丢失语句
2. 唇形驱动失效：数字人嘴形完全不动
3. 音画不同步：TTS播放异常，卡顿、失声

根本原因：
1. TTS消息队列处理不当，长文本被截断
2. 音频帧传递到唇形驱动的路径中断
3. 队列溢出导致帧丢失
4. 缺少完整的端到端流程验证
"""

import asyncio
import queue
import threading
import time
from typing import Any, Dict, Tuple

import numpy as np

from logger import logger


class DoubaoPlaybackOptimizer:
    """DoubaoTTS播放优化器"""

    def __init__(self, tts_instance, lip_asr=None):
        self.tts = tts_instance
        self.lip_asr = lip_asr

        # 消息处理状态跟踪
        self.processing_lock = threading.Lock()
        self.current_message = None
        self.message_queue = queue.Queue()

        # 音频帧统计
        self.audio_stats = {
            'total_sent': 0,
            'total_received': 0,
            'lost_frames': 0,
            'lip_driven_frames': 0
        }

        # 优化配置
        self.config = {
            'max_queue_size': 100,  # 防止队列无限增长
            'batch_size': 16,  # 唇形驱动批处理大小
            'lip_check_interval': 50,  # 每50帧检查一次唇形驱动状态
            'enable_direct_forward': True,  # 启用直接转发到唇形驱动
            'enable_queue_monitor': True  # 启用队列监控
        }

        # 状态监控
        self.lip_asr_ready = False
        self.audio_track_ready = False

    def setup_direct_forwarding(self):
        """设置直接转发路径，确保音频能到达唇形驱动"""
        logger.info("[OPTIMIZER] 设置直接转发路径")

        # 1. 确保TTS有lip_asr引用
        if hasattr(self.tts, 'parent') and hasattr(self.tts.parent, 'lip_asr'):
            self.lip_asr = self.tts.parent.lip_asr
            logger.info(f"[OPTIMIZER] 从parent获取lip_asr: {type(self.lip_asr)}")

        # 2. 检查lip_asr是否就绪
        if self.lip_asr:
            try:
                # 检查必要的队列和属性
                if hasattr(self.lip_asr, 'feat_queue') and hasattr(self.lip_asr, 'output_queue'):
                    self.lip_asr_ready = True
                    logger.info("[OPTIMIZER] LipASR就绪，特征队列可用")
                else:
                    logger.warning("[OPTIMIZER] LipASR缺少必要队列")
            except Exception as e:
                logger.error(f"[OPTIMIZER] LipASR检查失败: {e}")
        else:
            logger.error("[OPTIMIZER] LipASR不可用")

        # 3. 检查音频轨道
        if hasattr(self.tts, 'audio_track') and self.tts.audio_track:
            self.audio_track_ready = True
            logger.info("[OPTIMIZER] 音频轨道就绪")
        else:
            logger.warning("[OPTIMIZER] 音频轨道未就绪，将使用缓冲模式")

        return self.lip_asr_ready

    def patch_tts_methods(self):
        """修补TTS方法，确保完整处理"""
        logger.info("[OPTIMIZER] 修补TTS方法")

        # 保存原始方法
        if not hasattr(self.tts, '_original_stream_audio'):
            self.tts._original_stream_audio = self.tts.stream_audio

        # 替换为优化版本
        self.tts.stream_audio = self._optimized_stream_audio

        # 修补txt_to_audio以支持长文本分割
        if not hasattr(self.tts, '_original_txt_to_audio'):
            self.tts._original_txt_to_audio = self.tts.txt_to_audio

        self.tts.txt_to_audio = self._optimized_txt_to_audio

        logger.info("[OPTIMIZER] TTS方法修补完成")

    def _optimized_txt_to_audio(self, msg: Tuple[str, Dict]):
        """优化的文本到音频处理，支持长文本"""
        text, textevent = msg

        # 长文本分割（避免单次处理过大）
        max_length = 200  # 最大字符数
        if len(text) > max_length:
            logger.info(f"[OPTIMIZER] 长文本分割: {len(text)}字符")
            # 按标点分割
            import re
            segments = re.split(r'([。！？；,.!?;])', text)
            segments = [s.strip() for s in segments if s.strip()]

            # 重新组合成合理大小的块
            chunks = []
            current_chunk = ""
            for seg in segments:
                if len(current_chunk) + len(seg) < max_length:
                    current_chunk += seg
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = seg
            if current_chunk:
                chunks.append(current_chunk)

            logger.info(f"[OPTIMIZER] 分割为 {len(chunks)} 个块")

            # 逐块处理
            for i, chunk in enumerate(chunks):
                if self.tts.state != self.tts.state.RUNNING:
                    break

                logger.debug(
                    f"[OPTIMIZER] 处理块 {i+1}/{len(chunks)}: {chunk[:50]}...")
                chunk_msg = (chunk, textevent)
                self.tts._original_txt_to_audio(chunk_msg)
                time.sleep(0.05)  # 短暂间隔，避免过快
        else:
            # 原始处理
            self.tts._original_txt_to_audio(msg)

    def _optimized_stream_audio(self, audio_array, msg: Tuple[str, Dict]):
        """优化的音频流处理，确保完整传递"""
        text, textevent = msg
        streamlen = audio_array.shape[0]

        logger.debug(f"[OPTIMIZER] 开始流式传输: {len(text)}字符, {streamlen}样本")

        # 统计信息
        frames_sent = 0
        lip_frames_sent = 0
        start_time = time.time()

        # 缓冲区处理
        buffer = np.array([], dtype=np.float32)
        idx = 0
        first = True

        # 直接转发到唇形驱动的标志
        direct_to_lip = self.config['enable_direct_forward'] and self.lip_asr_ready

        if direct_to_lip:
            logger.info("[OPTIMIZER] 启用直接转发到唇形驱动")

        while idx < streamlen and self.tts.state == self.tts.state.RUNNING:
            # 添加到缓冲区
            buffer = np.concatenate(
                [buffer, audio_array[idx:idx+self.tts.chunk]])

            # 处理完整块
            while len(buffer) >= self.tts.chunk:
                audio_chunk = buffer[:self.tts.chunk]
                buffer = buffer[self.tts.chunk:]

                eventpoint = {}
                if first:
                    eventpoint = {'status': 'start', 'text': text}
                    eventpoint.update(**textevent)
                    first = False

                # 发送到音频轨道（WebRTC）
                if self.tts.audio_track and self.tts.loop:
                    self._send_to_audio_track(audio_chunk, eventpoint)
                    frames_sent += 1

                # 直接转发到唇形驱动
                if direct_to_lip and self.lip_asr:
                    self._forward_to_lip_asr(audio_chunk, eventpoint)
                    lip_frames_sent += 1

                # 发送到basereal（兼容旧逻辑）
                if hasattr(self.tts, 'parent') and not self.tts.audio_track:
                    self.tts.parent.put_audio_frame(audio_chunk, eventpoint)
                    frames_sent += 1

                # 队列监控
                if self.config['enable_queue_monitor'] and frames_sent % 20 == 0:
                    self._monitor_queues()

            idx += self.tts.chunk

        # 处理剩余缓冲区
        if len(buffer) > 0 and self.tts.state == self.tts.state.RUNNING:
            padded_chunk = np.zeros(self.tts.chunk, dtype=np.float32)
            padded_chunk[:len(buffer)] = buffer

            eventpoint = {'status': 'end', 'text': text}
            eventpoint.update(**textevent)

            if self.tts.audio_track and self.tts.loop:
                self._send_to_audio_track(padded_chunk, eventpoint)
                frames_sent += 1

            if direct_to_lip and self.lip_asr:
                self._forward_to_lip_asr(padded_chunk, eventpoint)
                lip_frames_sent += 1

            if hasattr(self.tts, 'parent') and not self.tts.audio_track:
                self.tts.parent.put_audio_frame(padded_chunk, eventpoint)
                frames_sent += 1
        else:
            # 发送结束事件
            eventpoint = {'status': 'end', 'text': text}
            eventpoint.update(**textevent)

            if self.tts.audio_track and self.tts.loop:
                self._send_to_audio_track(
                    np.zeros(self.tts.chunk, np.float32), eventpoint)
                frames_sent += 1

            if direct_to_lip and self.lip_asr:
                self._forward_to_lip_asr(
                    np.zeros(self.tts.chunk, np.float32), eventpoint)
                lip_frames_sent += 1

            if hasattr(self.tts, 'parent') and not self.tts.audio_track:
                self.tts.parent.put_audio_frame(
                    np.zeros(self.tts.chunk, np.float32), eventpoint)
                frames_sent += 1

        # 更新统计
        elapsed = time.time() - start_time
        self.audio_stats['total_sent'] += frames_sent
        self.audio_stats['lip_driven_frames'] += lip_frames_sent

        logger.info(
            f"[OPTIMIZER] 流式传输完成: {frames_sent}帧, {lip_frames_sent}唇形帧, 耗时{elapsed:.2f}s")

        # 性能警告
        if elapsed > 5.0:
            logger.warning(f"[OPTIMIZER] 处理时间过长: {elapsed:.2f}s")
        if frames_sent == 0:
            logger.error("[OPTIMIZER] 没有发送任何音频帧!")

    def _send_to_audio_track(self, audio_chunk, eventpoint):
        """发送到音频轨道"""
        try:
            # 转换为16-bit PCM
            frame = (audio_chunk * 32767).astype(np.int16)
            frame_2d = frame.reshape(1, -1)

            # 创建AudioFrame
            from av import AudioFrame
            audio_frame = AudioFrame.from_ndarray(
                frame_2d, layout='mono', format='s16')
            audio_frame.sample_rate = 16000

            # 发送到WebRTC队列
            if self.tts.audio_track and self.tts.loop:
                try:
                    # 直接调用队列的put方法，不使用call_soon_threadsafe（因为已经在正确的线程中）
                    self.tts.audio_track._queue.put_nowait(
                        (audio_frame, eventpoint))
                    logger.debug(f"[OPTIMIZER] 音频帧发送到WebRTC")
                except asyncio.QueueFull:
                    logger.warning(f"[OPTIMIZER] WebRTC队列满，丢弃帧")
                except Exception as e:
                    logger.error(f"[OPTIMIZER] 发送到WebRTC失败: {e}")
            else:
                logger.warning(f"[OPTIMIZER] 音频轨道或循环不可用")
        except Exception as e:
            logger.error(f"[OPTIMIZER] 音频帧创建失败: {e}")

    def _forward_to_lip_asr(self, audio_chunk, eventpoint):
        """直接转发到唇形驱动"""
        try:
            if not self.lip_asr:
                return

            # 确保音频格式正确
            if isinstance(audio_chunk, np.ndarray):
                # 转换为float32（LipASR期望的格式）
                audio_data = audio_chunk.astype(np.float32)

                # 转发到LipASR
                if hasattr(self.lip_asr, 'put_audio_frame'):
                    self.lip_asr.put_audio_frame(audio_data, eventpoint)
                    logger.debug(f"[OPTIMIZER] 音频转发到LipASR")
                else:
                    logger.error(f"[OPTIMIZER] LipASR缺少put_audio_frame方法")
            else:
                logger.error(f"[OPTIMIZER] 音频数据格式错误: {type(audio_chunk)}")
        except Exception as e:
            logger.error(f"[OPTIMIZER] 转发到LipASR失败: {e}")

    def _monitor_queues(self):
        """监控队列状态"""
        if not self.config['enable_queue_monitor']:
            return

        try:
            # 检查WebRTC队列
            if self.tts.audio_track:
                webrtc_size = self.tts.audio_track._queue.qsize()
                if webrtc_size > 50:
                    logger.warning(f"[OPTIMIZER] WebRTC队列过大: {webrtc_size}")

            # 检查LipASR队列
            if self.lip_asr:
                if hasattr(self.lip_asr, 'feat_queue'):
                    feat_size = self.lip_asr.feat_queue.qsize()
                    if feat_size > 30:
                        logger.warning(
                            f"[OPTIMIZER] LipASR特征队列过大: {feat_size}")

                if hasattr(self.lip_asr, 'output_queue'):
                    output_size = self.lip_asr.output_queue.qsize()
                    if output_size > 30:
                        logger.warning(
                            f"[OPTIMIZER] LipASR输出队列过大: {output_size}")

        except Exception as e:
            logger.debug(f"[OPTIMIZER] 队列监控异常: {e}")

    def verify_lip_driving(self, duration=5):
        """验证唇形驱动是否正常工作"""
        logger.info(f"[OPTIMIZER] 开始验证唇形驱动，持续{duration}秒")

        if not self.lip_asr:
            logger.error("[OPTIMIZER] LipASR不可用，无法验证")
            return False

        # 检查队列是否在增长
        initial_output_size = 0
        if hasattr(self.lip_asr, 'output_queue'):
            initial_output_size = self.lip_asr.output_queue.qsize()

        start_time = time.time()
        frames_processed = 0

        while time.time() - start_time < duration:
            try:
                # 尝试获取唇形驱动输出
                if hasattr(self.lip_asr, 'output_queue'):
                    frame, idx, audio_frames = self.lip_asr.output_queue.get(
                        timeout=0.5)
                    frames_processed += 1
                    logger.debug(f"[OPTIMIZER] 收到唇形帧: {idx}")
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[OPTIMIZER] 获取唇形帧失败: {e}")
                break

        # 结果评估
        success = frames_processed > 0
        if success:
            logger.info(f"[OPTIMIZER] ✅ 唇形驱动验证成功: {frames_processed}帧")
        else:
            logger.error(f"[OPTIMIZER] ❌ 唇形驱动验证失败: 没有收到任何帧")

        return success

    def get_status_report(self):
        """获取状态报告"""
        return {
            'lip_asr_ready': self.lip_asr_ready,
            'audio_track_ready': self.audio_track_ready,
            'audio_stats': self.audio_stats.copy(),
            'config': self.config.copy()
        }


def apply_optimization(tts_instance, lip_asr=None):
    """应用优化到TTS实例"""
    logger.info("=" * 60)
    logger.info("应用DoubaoTTS播放优化")
    logger.info("=" * 60)

    optimizer = DoubaoPlaybackOptimizer(tts_instance, lip_asr)

    # 1. 设置直接转发
    optimizer.setup_direct_forwarding()

    # 2. 修补方法
    optimizer.patch_tts_methods()

    # 3. 返回优化器（可用于后续监控）
    return optimizer


# 使用示例和测试
if __name__ == "__main__":
    print("DoubaoTTS播放优化模块")
    print("=" * 50)
    print("本模块用于解决以下问题:")
    print("1. 长对话消息丢失")
    print("2. 唇形驱动失效")
    print("3. 音画不同步")
    print("=" * 50)
    print("使用方法:")
    print("在ttsreal.py的DoubaoTTS类中:")
    print("  from fixes.optimize_doubao_playback import apply_optimization")
    print("  # 在__init__或render方法中调用:")
    print("  self.optimizer = apply_optimization(self, self.parent.lip_asr)")
