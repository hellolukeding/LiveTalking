#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Doubao WebSocket连接管理器
解决重复初始化问题，实现连接复用和连接池管理
"""

import asyncio
import json
import threading
import time
import uuid
from queue import Queue
from typing import Any, Dict, Optional

import websocket

from logger import logger


class DoubaoWebSocketConnection:
    """单个WebSocket连接包装器"""

    def __init__(self, appid: str, token: str, voice_id: str):
        self.appid = appid
        self.token = token
        self.voice_id = voice_id
        self.cluster = "volcano_tts"

        self.ws = None
        self.is_connected = False
        self.last_used = time.time()
        self.request_count = 0
        self.error_count = 0

        # 连接状态
        self.lock = threading.Lock()

    def connect(self) -> bool:
        """建立WebSocket连接"""
        if self.is_connected and self.ws:
            return True

        try:
            api_url = f"wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
            self.ws = websocket.create_connection(api_url, timeout=10)
            self.is_connected = True
            self.last_used = time.time()
            logger.info(f"[WS_MANAGER] WebSocket连接成功建立")
            return True
        except Exception as e:
            logger.error(f"[WS_MANAGER] WebSocket连接失败: {e}")
            self.is_connected = False
            self.error_count += 1
            return False

    def send_text_request(self, text: str, reqid: str) -> bool:
        """发送文本转语音请求"""
        if not self.is_connected or not self.ws:
            logger.warning("[WS_MANAGER] 连接未就绪，尝试重连...")
            if not self.connect():
                return False

        try:
            request_json = {
                "app": {
                    "appid": self.appid,
                    "token": self.token,
                    "cluster": self.cluster
                },
                "user": {
                    "uid": str(uuid.uuid4())
                },
                "audio": {
                    "voice_type": self.voice_id,
                    "encoding": "pcm",
                    "rate": 16000,
                    "speed_ratio": 1.0,
                    "volume_ratio": 1.0,
                    "pitch_ratio": 1.0,
                },
                "request": {
                    "reqid": reqid,
                    "text": text,
                    "text_type": "plain",
                    "operation": "submit"
                }
            }

            with self.lock:
                self.ws.send(json.dumps(request_json))
                self.last_used = time.time()
                self.request_count += 1

            logger.debug(f"[WS_MANAGER] 请求发送成功: reqid={reqid}")
            return True

        except Exception as e:
            logger.error(f"[WS_MANAGER] 发送请求失败: {e}")
            self.error_count += 1
            self.is_connected = False
            return False

    def receive_audio_chunk(self, timeout: float = 30.0) -> Optional[bytes]:
        """接收音频数据块"""
        if not self.is_connected or not self.ws:
            return None

        try:
            with self.lock:
                self.ws.settimeout(timeout)
                result = self.ws.recv()
                self.last_used = time.time()

            return result

        except Exception as e:
            logger.error(f"[WS_MANAGER] 接收数据失败: {e}")
            self.error_count += 1
            self.is_connected = False
            return None

    def close(self):
        """关闭连接"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.is_connected = False
        logger.info(f"[WS_MANAGER] WebSocket连接已关闭")

    def is_idle(self, timeout: int = 300) -> bool:
        """检查连接是否空闲超时"""
        return time.time() - self.last_used > timeout

    def is_healthy(self) -> bool:
        """检查连接健康状态"""
        return self.is_connected and self.error_count < 3


class DoubaoConnectionPool:
    """WebSocket连接池管理器"""

    def __init__(self, appid: str, token: str, voice_id: str, max_connections: int = 3):
        self.appid = appid
        self.token = token
        self.voice_id = voice_id
        self.max_connections = max_connections

        self.connections: list[DoubaoWebSocketConnection] = []
        self.available_connections: Queue[DoubaoWebSocketConnection] = Queue()
        self.active_requests: Dict[str, DoubaoWebSocketConnection] = {}

        self.lock = threading.Lock()
        self.cleanup_thread = None
        self.running = False

        # 统计信息
        self.total_requests = 0
        self.total_reuses = 0

        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """启动清理线程"""
        self.running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()

    def _cleanup_worker(self):
        """清理空闲连接"""
        while self.running:
            time.sleep(60)  # 每分钟检查一次
            try:
                self._cleanup_idle_connections()
            except Exception as e:
                logger.error(f"[WS_POOL] 清理线程异常: {e}")

    def _cleanup_idle_connections(self):
        """清理空闲连接"""
        with self.lock:
            to_remove = []
            for conn in self.connections:
                if conn.is_idle(timeout=300):  # 5分钟空闲
                    to_remove.append(conn)

            for conn in to_remove:
                if conn in self.connections:
                    self.connections.remove(conn)
                if conn in self.available_connections.queue:
                    # 从队列中移除
                    temp_queue = Queue()
                    while not self.available_connections.empty():
                        c = self.available_connections.get()
                        if c != conn:
                            temp_queue.put(c)
                    self.available_connections = temp_queue

                conn.close()
                logger.info(f"[WS_POOL] 移除空闲连接，当前连接数: {len(self.connections)}")

    def _create_connection(self) -> Optional[DoubaoWebSocketConnection]:
        """创建新连接"""
        if len(self.connections) >= self.max_connections:
            logger.warning(f"[WS_POOL] 已达到最大连接数限制: {self.max_connections}")
            return None

        conn = DoubaoWebSocketConnection(self.appid, self.token, self.voice_id)
        if conn.connect():
            with self.lock:
                self.connections.append(conn)
                logger.info(
                    f"[WS_POOL] 创建新连接成功，当前连接数: {len(self.connections)}")
            return conn
        return None

    def get_connection(self, timeout: float = 5.0) -> Optional[DoubaoWebSocketConnection]:
        """获取可用连接"""
        start_time = time.time()

        # 1. 尝试从可用队列获取
        try:
            conn = self.available_connections.get(timeout=0.1)
            if conn and conn.is_healthy():
                self.total_reuses += 1
                logger.debug(f"[WS_POOL] 复用现有连接，总复用次数: {self.total_reuses}")
                return conn
        except:
            pass

        # 2. 尝试创建新连接
        with self.lock:
            if len(self.connections) < self.max_connections:
                conn = self._create_connection()
                if conn:
                    return conn

        # 3. 等待可用连接
        while time.time() - start_time < timeout:
            try:
                conn = self.available_connections.get(timeout=0.5)
                if conn and conn.is_healthy():
                    self.total_reuses += 1
                    return conn
            except:
                pass

            # 检查是否可以创建新连接
            with self.lock:
                if len(self.connections) < self.max_connections:
                    conn = self._create_connection()
                    if conn:
                        return conn

        logger.error("[WS_POOL] 获取连接超时")
        return None

    def return_connection(self, conn: DoubaoWebSocketConnection):
        """归还连接到池"""
        if not conn or not conn.is_healthy():
            # 连接不健康，移除它
            with self.lock:
                if conn in self.connections:
                    self.connections.remove(conn)
                    conn.close()
            return

        # 检查错误次数
        if conn.error_count >= 3:
            logger.warning(f"[WS_POOL] 连接错误次数过多，移除连接")
            with self.lock:
                if conn in self.connections:
                    self.connections.remove(conn)
                    conn.close()
            return

        # 归还到可用队列
        self.available_connections.put(conn)
        logger.debug(f"[WS_POOL] 连接已归还")

    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计"""
        return {
            "total_connections": len(self.connections),
            "available_connections": self.available_connections.qsize(),
            "total_requests": self.total_requests,
            "total_reuses": self.total_reuses,
            "active_requests": len(self.active_requests),
            "max_connections": self.max_connections
        }

    def shutdown(self):
        """关闭所有连接"""
        self.running = False
        with self.lock:
            for conn in self.connections:
                conn.close()
            self.connections.clear()
            # 清空队列
            while not self.available_connections.empty():
                try:
                    self.available_connections.get_nowait()
                except:
                    break
        logger.info("[WS_POOL] 连接池已关闭")


class DoubaoTTSConnectionManager:
    """DoubaoTTS连接管理器 - 优化版"""

    def __init__(self, opt, parent):
        self.opt = opt
        self.parent = parent

        # 配置
        self.appid = os.getenv("DOUBAO_APPID")
        self.token = os.getenv("DOUBAO_TOKEN")
        self.voice_id = os.getenv("DOUBAO_VOICE_ID") or opt.REF_FILE

        # 连接池
        self.connection_pool = DoubaoConnectionPool(
            appid=self.appid,
            token=self.token,
            voice_id=self.voice_id,
            max_connections=3  # 最大3个并发连接
        )

        # 优化器
        self.optimizer = None
        self._auto_integrate_optimizer()

        logger.info("[DOUBAO_TTS] 连接管理器初始化完成")

    def _auto_integrate_optimizer(self):
        """自动集成优化器"""
        try:
            from test_optimization.ultra_noise_reduction import \
                UltraNoiseReductionOptimizer
            self.optimizer = UltraNoiseReductionOptimizer(
                self, getattr(self.parent, 'lip_asr', None))
            logger.info("[DOUBAO_TTS] 优化器集成成功")
        except Exception as e:
            logger.warning(f"[DOUBAO_TTS] 优化器集成失败: {e}")

    def process_text(self, text: str, textevent: dict) -> bool:
        """处理文本转语音"""
        reqid = str(uuid.uuid4())
        logger.info(f"[DOUBAO_TTS] 开始处理: {text[:20]}... (reqid={reqid})")

        # 获取连接
        conn = self.connection_pool.get_connection()
        if not conn:
            logger.error("[DOUBAO_TTS] 无法获取连接")
            return False

        try:
            # 发送请求
            if not conn.send_text_request(text, reqid):
                logger.error("[DOUBAO_TTS] 发送请求失败")
                self.connection_pool.return_connection(conn)
                return False

            # 流式接收音频
            first_chunk = True
            audio_buffer = np.array([], dtype=np.float32)

            while self.parent.state == State.RUNNING:
                result = conn.receive_audio_chunk(timeout=30.0)

                if result is None:
                    break

                # 检查结束标志
                if isinstance(result, str):
                    try:
                        result_json = json.loads(result)
                        if result_json.get("code") != 0:
                            logger.error(f"[DOUBAO_TTS] 错误响应: {result_json}")
                        break
                    except:
                        break

                # 解析音频数据
                if len(result) < 4:
                    continue

                header_size = int.from_bytes(result[0:4], "big")
                payload = result[header_size:]

                if len(payload) > 0:
                    # 转换为音频数据
                    audio_chunk = np.frombuffer(
                        payload, dtype=np.int16).astype(np.float32) / 32767.0

                    # 累积到缓冲区（用于优化器处理）
                    audio_buffer = np.concatenate([audio_buffer, audio_chunk])

                    # 如果没有优化器，直接推送
                    if self.optimizer is None:
                        self._push_audio_chunks(
                            audio_buffer, textevent, first_chunk)
                        audio_buffer = np.array([], dtype=np.float32)
                        first_chunk = False

            # 处理剩余音频
            if len(audio_buffer) > 0:
                if self.optimizer:
                    # 使用优化器处理
                    self.optimizer.optimized_stream_audio(
                        audio_buffer, (text, textevent))
                else:
                    self._push_audio_chunks(
                        audio_buffer, textevent, first_chunk)

            # 发送结束事件
            self._send_end_event(textevent)

            # 归还连接
            self.connection_pool.return_connection(conn)

            logger.info(f"[DOUBAO_TTS] 处理完成: {text[:20]}...")
            return True

        except Exception as e:
            logger.error(f"[DOUBAO_TTS] 处理异常: {e}")
            self.connection_pool.return_connection(conn)
            return False

    def _push_audio_chunks(self, audio_array: np.ndarray, textevent: dict, first_chunk: bool):
        """推送音频块"""
        idx = 0
        chunk_size = 320  # 20ms

        while idx < len(audio_array):
            end = idx + chunk_size
            if end <= len(audio_array):
                chunk = audio_array[idx:end]
                idx = end
            else:
                # 补零
                chunk = np.zeros(chunk_size, dtype=np.float32)
                valid_len = len(audio_array) - idx
                chunk[:valid_len] = audio_array[idx:]
                idx = len(audio_array)

            eventpoint = {}
            if first_chunk:
                eventpoint = {'status': 'start',
                              'text': textevent.get('text', '')}
                eventpoint.update(textevent)
                first_chunk = False

            # 推送音频
            if getattr(self, 'direct_to_webrtc', False):
                self._send_to_webrtc(chunk, eventpoint)
            else:
                self.parent.put_audio_frame(chunk, eventpoint)

    def _send_end_event(self, textevent: dict):
        """发送结束事件"""
        eventpoint = {'status': 'end', 'text': textevent.get('text', '')}
        eventpoint.update(textevent)

        if getattr(self, 'direct_to_webrtc', False):
            self._send_to_webrtc(np.zeros(320, dtype=np.float32), eventpoint)
        else:
            self.parent.put_audio_frame(
                np.zeros(320, dtype=np.float32), eventpoint)

    def _send_to_webrtc(self, audio_chunk: np.ndarray, eventpoint: dict):
        """发送到WebRTC"""
        try:
            from av import AudioFrame
            frame = (audio_chunk * 32767).astype(np.int16)
            frame_2d = frame.reshape(1, -1)
            audio_frame = AudioFrame.from_ndarray(
                frame_2d, layout='mono', format='s16')
            audio_frame.sample_rate = 16000

            if self.parent.audio_track and self.parent.loop:
                try:
                    self.parent.loop.call_soon_threadsafe(
                        self.parent.audio_track._queue.put_nowait, (audio_frame, eventpoint))
                except:
                    pass
        except Exception as e:
            logger.error(f"WebRTC发送失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pool_stats = self.connection_pool.get_stats()
        return {
            "connection_pool": pool_stats,
            "optimizer_enabled": self.optimizer is not None
        }

    def shutdown(self):
        """关闭管理器"""
        self.connection_pool.shutdown()
        logger.info("[DOUBAO_TTS] 连接管理器已关闭")


# 使用示例
if __name__ == "__main__":
    # 模拟配置
    class MockOpt:
        def __init__(self):
            self.REF_FILE = "female"
            self.fps = 25

    class MockParent:
        def __init__(self):
            self.state = State.RUNNING
            self.audio_track = None
            self.loop = None

        def put_audio_frame(self, chunk, eventpoint):
            print(f"推送音频: {len(chunk)} samples")

    # 设置环境变量
    os.environ["DOUBAO_APPID"] = "test_appid"
    os.environ["DOUBAO_TOKEN"] = "test_token"
    os.environ["DOUBAO_VOICE_ID"] = "female"

    opt = MockOpt()
    parent = MockParent()

    # 创建管理器
    manager = DoubaoTTSConnectionManager(opt, parent)

    # 测试统计
    print("初始统计:", manager.get_stats())
