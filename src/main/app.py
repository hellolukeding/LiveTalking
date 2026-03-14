
# 启动前依赖检查
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
dep_check_script = project_root / "scripts" / "ensure_deps.py"
if dep_check_script.exists():
    result = subprocess.run([sys.executable, str(dep_check_script)],
                                  capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        sys.exit(1)

###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import argparse
# Global args (set after parse_args())
args = None
import asyncio
import base64
import gc
import json
import sys
import threading
import traceback
from contextlib import asynccontextmanager
import os
import random
import re
import shutil
import sys
from threading import Event, Thread
from typing import Dict

import aiohttp
import numpy as np
import torch
import torch.multiprocessing as mp
from aiohttp import web
from aiortc import (RTCConfiguration, RTCIceServer, RTCPeerConnection,
                    RTCSessionDescription)
from aiortc.rtcrtpsender import RTCRtpSender
from aiortc.rtcrtpparameters import RTCRtpParameters, RTCRtpEncodingParameters
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_sockets import Sockets

from basereal import BaseReal
from llm import llm_response
from logger import logger
from webrtc import HumanPlayer
from services.avatar_manager import (
    list_avatars, get_avatar, update_avatar, delete_avatar,
    generate_avatar_async
)

load_dotenv()

# import gevent
# from gevent import pywsgi
# from geventwebsocket.handler import WebSocketHandler

# import multiprocessing
# server.py


app = Flask(__name__)
# sockets = Sockets(app)
nerfreals: Dict[int, BaseReal] = {}  # sessionid:BaseReal
opt = None
model = None
avatar = None


##### webrtc###############################
pcs = set()
webrtc_players: Dict[int, HumanPlayer] = {}  # sessionid:HumanPlayer

# ========== 安全修复：频率限制器和会话锁 ==========
import time
from collections import defaultdict

class RateLimiter:
    """简单的频率限制器，防止 DoS 攻击"""
    def __init__(self, max_requests=60, window=60):
        self.max_requests = max_requests  # 时间窗口内最多请求数
        self.window = window  # 时间窗口（秒）
        self.requests = defaultdict(list)  # 每个客户端的请求记录

    def is_allowed(self, client_id):
        now = time.time()
        # 清理过期请求
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window
        ]
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        self.requests[client_id].append(now)
        return True

# 全局频率限制器和会话锁（在应用启动后初始化）
# 注意：不在模块级别声明，直接在 main 函数中初始化

# 安全常量
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB 最大音频文件大小
MAX_TEXT_LENGTH = 10000  # 最大文本长度

# ========== 全局超时保护配置 ==========
GLOBAL_REQUEST_TIMEOUT = 60  # 全局请求超时（秒）
HANDLER_TIMEOUT = 90  # 各个处理器的超时（秒）
HEARTBEAT_INTERVAL = 30  # 心跳检测间隔（秒）

# 全局超时统计（用于监控）
timeout_stats = {
    'timeouts': 0,
    'last_timeout': None,
    'active_requests': set()
}

@asynccontextmanager
async def timeout_context(timeout_sec: float, request_info: str = ""):
    """
    全局超时上下文管理器
    
    使用 asyncio.timeout() (Python 3.11+) 而不是 wait_for
    更好的异常处理和资源清理
    """
    task = asyncio.current_task()
    request_id = id(task)
    
    # 记录活跃请求
    timeout_stats['active_requests'].add(request_id)
    
    # 使用 asyncio.timeout 创建超时上下文
    async with asyncio.timeout(timeout_sec) as timeout_cm:
        try:
            yield timeout_cm
        except asyncio.TimeoutError:
            timeout_stats['timeouts'] += 1
            timeout_stats['last_timeout'] = {
                'time': time.time(),
                'request': request_info,
                'task': str(task)
            }
            logger.warning(f"[超时] 请求超时: {request_info} (任务: {task.get_name()})")
            raise
        finally:
            timeout_stats['active_requests'].discard(request_id)


async def timeout_middleware_factory(app, handler):
    """
    全局超时中间件 - 保护所有请求
    
    自动为所有请求添加超时保护
    """
    async def middleware_handler(request):
        request_path = request.path
        request_method = request.method
        
        # 为所有请求添加全局超时保护
        try:
            async with timeout_context(GLOBAL_REQUEST_TIMEOUT, f"{request_method} {request_path}"):
                response = await handler(request)
                return response
        except asyncio.TimeoutError:
            return web.Response(
                status=504,
                text=json.dumps({
                    "code": -1,
                    "msg": "请求处理超时",
                    "timeout": GLOBAL_REQUEST_TIMEOUT
                }),
                content_type="application/json"
            )
        except Exception as e:
            logger.exception(f"[中间件] 请求处理异常: {request_path}")
            return web.Response(
                status=500,
                text=json.dumps({
                    "code": -1,
                    "msg": f"服务器错误: {str(e)}"
                }),
                content_type="application/json"
            )
    
    return middleware_handler


async def safe_request_json(request, max_size=1024*1024):
    """
    安全的 JSON 请求解析，带超时保护
    
    解决 request.json() 永久挂起的问题
    """
    try:
        # 添加读取超时
        async with asyncio.timeout(5):  # 5秒超时
            # 先检查 content-length
            if request.content_length and request.content_length > max_size:
                raise ValueError(f"请求体过大: {request.content_length} > {max_size}")
            
            data = await request.json()
            return data
    except asyncio.TimeoutError:
        logger.error(f"[请求] JSON 解析超时")
        raise ValueError("请求读取超时")
    except Exception as e:
        logger.error(f"[请求] JSON 解析失败: {e}")
        raise


async def safe_request_post(request, max_size=MAX_AUDIO_SIZE):
    """
    安全的 POST 表单解析，带超时保护
    
    解决 request.post() 永久挂起的问题
    """
    try:
        async with asyncio.timeout(5):  # 5秒超时
            # 先检查 content-length
            if request.content_length and request.content_length > max_size:
                raise ValueError(f"请求体过大: {request.content_length} > {max_size}")
            
            form = await request.post()
            return form
    except asyncio.TimeoutError:
        logger.error(f"[请求] POST 表单解析超时")
        raise ValueError("请求读取超时")
    except Exception as e:
        logger.error(f"[请求] POST 表单解析失败: {e}")
        raise


async def monitor_task():
    """监控任务：检测异常状态并记录"""
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            logger.info("[监控] 监控任务运行中...")  # 添加心跳日志
            
            # 检查活跃请求数量
            active_count = len(timeout_stats['active_requests'])
            if active_count > 0:
                logger.info(f"[监控] 活跃请求: {active_count}")
            
            # 检查超时统计
            if timeout_stats['timeouts'] > 0:
                logger.warning(f"[监控] 超时统计: 总计 {timeout_stats['timeouts']} 次")
                if timeout_stats['last_timeout']:
                    last = timeout_stats['last_timeout']
                    logger.warning(f"[监控] 最后超时: {last}")
            
            # 检查会话状态
            session_count = len(nerfreals)
            if session_count > 0:
                logger.info(f"[监控] 活跃会话: {session_count}")
                
                # 检查是否有僵尸会话（会话存在但没有活动）
                cleanup_count = 0
                for sessionid in list(nerfreals.keys()):
                    nerfreal = nerfreals[sessionid]
                    if nerfreal is None:
                        logger.warning(f"[监控] 发现僵尸会话: {sessionid} (None)")
                        del nerfreals[sessionid]
                        cleanup_count += 1
                    elif not hasattr(nerfreal, 'datachannel') or nerfreal.datachannel is None:
                        logger.warning(f"[监控] 发现僵尸会话: {sessionid} (无 datachannel)")
                        try:
                            if hasattr(nerfreal, 'stop_all_threads'):
                                nerfreal.stop_all_threads()
                        except:
                            pass
                        del nerfreals[sessionid]
                        cleanup_count += 1
                
                if cleanup_count > 0:
                    logger.info(f"[监控] 已清理 {cleanup_count} 个僵尸会话")
                
        except Exception as e:
            logger.error(f"[监控] 监控任务异常: {e}")
    

    pagename = 'webrtcapi.html'
    if opt.transport == 'rtmp':
        pagename = 'echoapi.html'
    elif opt.transport == 'rtcpush':
        pagename = 'rtcpushapi.html'
    logger.info('start http server; http://<serverip>:' +
                str(opt.listenport)+'/'+pagename)
    logger.info('如果使用webrtc，推荐访问webrtc集成前端: http://<serverip>:' +
                str(opt.listenport)+'/dashboard.html')



def randN(N) -> int:
    '''生成长度为 N的随机数 '''
    min = pow(10, N - 1)
    max = pow(10, N)
    return random.randint(min, max - 1)


# ========== 全局锁优化 ==========
# 使用 try_lock 避免死锁，并提供锁超时
async def safe_nerfreals_operation(timeout_sec=5):
    """
    安全的 nerfreals 操作上下文管理器
    
    使用 try_lock 避免永久死锁
    如果获取锁失败，记录警告但不阻塞
    """
    acquired = False
    try:
        acquired = await asyncio.wait_for(nerfreals_lock.acquire(), timeout=timeout_sec)
        if acquired:
            yield
        else:
            logger.warning("[锁] 无法获取 nerfreals_lock，跳过操作")
            yield None  # 返回 None 表示跳过
    except asyncio.TimeoutError:
        logger.warning(f"[锁] 获取 nerfreals_lock 超时 ({timeout_sec}s)")
        yield None
    finally:
        if acquired:
            nerfreals_lock.release()


def build_nerfreal(sessionid: int, avatar_id: str) -> BaseReal:
    # 创建副本避免修改全局 opt
    import copy
    opt_copy = copy.copy(opt)
    opt_copy.sessionid = sessionid

    # 按会话加载 avatar（不再使用全局 avatar）
    # 从 meta.json 读取 avatar 名字和 voice_id
    import json
    meta_path = f"./data/avatars/{avatar_id}/meta.json"
    avatar_name = avatar_id  # 默认使用 avatar_id
    voice_id = getattr(opt_copy, 'REF_FILE', 'zh_female_wenroushunshun_mars_bigtts')  # 默认语音
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
            avatar_name = meta.get('name', avatar_id)
            voice_id = meta.get('voice_id', voice_id)
    except Exception as e:
        logger.warning(f"[BUILD] Failed to load meta.json for {avatar_id}: {e}")

    # 设置 voice_id 到 opt.REF_FILE（TTS 使用）
    opt_copy.REF_FILE = voice_id

    logger.info(f"[BUILD] Loaded avatar for session {sessionid}: {avatar_id}, name: {avatar_name}, voice_id: {voice_id}")

    if opt_copy.model == 'wav2lip':
        from lipreal import load_avatar, LipReal
        frame_list, face_list, coord_list, _ = load_avatar(avatar_id)
        nerfreal = LipReal(opt_copy, model, (frame_list, face_list, coord_list), avatar_name)
    elif opt_copy.model == 'musetalk':
        from musereal import load_avatar, MuseReal
        frame_list, mask_list, coord_list, mask_coords, latents = load_avatar(avatar_id)
        nerfreal = MuseReal(opt_copy, model, (frame_list, mask_list, coord_list, mask_coords, latents), avatar_name)
    # elif opt_copy.model == 'ernerf':
    #     from nerfreal import NeRFReal
    #     nerfreal = NeRFReal(opt_copy,model,session_avatar)
    elif opt_copy.model == 'ultralight':
        from lightreal import load_avatar, LightReal
        ultralight_model, frame_list, face_list, coord_list = load_avatar(avatar_id)
        nerfreal = LightReal(opt_copy, model, (ultralight_model, frame_list, face_list, coord_list), avatar_name)
    return nerfreal

# @app.route('/offer', methods=['POST'])


async def offer(request):
    try:
        params = await safe_request_json(request)
        logger.debug(f"[OFFER] Received offer request: {params}")

        if not params or 'sdp' not in params or 'type' not in params:
            logger.error("[OFFER] Invalid request parameters")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": "Invalid request: missing sdp or type"}),
                status=400
            )

        # Validate avatar_id parameter
        avatar_id = params.get('avatar_id')
        if not avatar_id:
            logger.error("[OFFER] avatar_id is required")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "avatar_id is required"}),
                status=400
            )

        # Validate avatar_id format (only alphanumeric, underscore, hyphen)
        if not re.match(r'^[a-zA-Z0-9_-]+$', avatar_id):
            logger.error(f"[OFFER] Invalid avatar_id format: {avatar_id}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid avatar_id format"}),
                status=400
            )

        # Enforce maximum length (64 characters)
        if len(avatar_id) > 64:
            logger.error(f"[OFFER] avatar_id too long: {len(avatar_id)}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "avatar_id exceeds maximum length"}),
                status=400
            )

        # Validate avatar exists and is ready
        avatar_meta = get_avatar(avatar_id)
        if not avatar_meta:
            logger.error(f"[OFFER] Avatar not found: {avatar_id}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"Avatar not found: {avatar_id}"}),
                status=400
            )

        if avatar_meta.get('status') != 'ready':
            logger.error(f"[OFFER] Avatar not ready: {avatar_id}, status={avatar_meta.get('status')}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"Avatar not ready: {avatar_id}"}),
                status=400
            )

        logger.info(f"[OFFER] Using avatar: {avatar_id}")

        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        logger.debug(
            f"[OFFER] Created RTCSessionDescription: type={params['type']}")

        # Check session limit with lock to prevent race conditions
        async with nerfreals_lock:
            if len(nerfreals) >= opt.max_session:
                logger.warning(
                    f"[OFFER] Max session limit reached: {len(nerfreals)} >= {opt.max_session}")
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"code": -1, "msg": "reach max session"}),
                    status=429
                )

        sessionid = randN(6)
        logger.debug(f"[OFFER] Generating session ID: {sessionid}")

        # Initialize session with error handling
        try:
            # Reserve session slot with lock
            async with nerfreals_lock:
                if len(nerfreals) >= opt.max_session:
                    return web.Response(
                        content_type="application/json",
                        text=json.dumps({"code": -1, "msg": "reach max session"}),
                        status=429
                    )
                nerfreals[sessionid] = None

            logger.debug(f"[OFFER] Building nerfreal for session {sessionid}")

            # Build nerfreal in executor to avoid blocking (with timeout)
            try:
                nerfreal = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, avatar_id),
                    timeout=30.0  # 30 秒超时
                )
            except asyncio.TimeoutError:
                logger.error(f"[OFFER] 构建超时，会话 {sessionid}")
                async with nerfreals_lock:
                    if sessionid in nerfreals:
                        del nerfreals[sessionid]
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"code": -1, "msg": "初始化超时"}),
                    status=504
                )

            if nerfreal is None:
                raise RuntimeError("Failed to build nerfreal instance")

            # Update nerfreal with lock
            async with nerfreals_lock:
                nerfreals[sessionid] = nerfreal
            logger.debug(
                f"[OFFER] Nerfreal built successfully for session {sessionid}")

        except Exception as e:
            logger.error(f"[OFFER] Failed to build nerfreal: {str(e)}")
            async with nerfreals_lock:
                if sessionid in nerfreals:
                    del nerfreals[sessionid]
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Failed to initialize session: {str(e)}"}),
                status=500
            )

        # Create WebRTC peer connection
        try:
            # 本地 STUN 服务器 (coturn)
            ice_servers = [
                # 本地 STUN 服务器 (最快)
                RTCIceServer(urls='stun:192.168.1.132:3478'),
                
                # 腾讯云 STUN (备用)
                RTCIceServer(urls='stun:stun.qq.com:3478'),
            ]
            pc = RTCPeerConnection(
                configuration=RTCConfiguration(iceServers=ice_servers))
            pcs.add(pc)
            logger.debug(
                f"[OFFER] WebRTC peer connection created for session {sessionid}")

        except Exception as e:
            logger.error(f"[OFFER] Failed to create peer connection: {str(e)}")
            if sessionid in nerfreals:
                del nerfreals[sessionid]
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Failed to create peer connection: {str(e)}"}),
                status=500
            )

        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.debug(
                f"[WEBRTC] Data channel created: {channel.label} for session {sessionid}")
            try:
                nerfreals[sessionid].datachannel = channel
                nerfreals[sessionid].loop = asyncio.get_event_loop()
                logger.debug(
                    f"[WEBRTC] Data channel initialized for session {sessionid}")
            except Exception as e:
                logger.error(
                    f"[WEBRTC] Failed to initialize data channel: {str(e)}")

        @pc.on("track")
        def on_track(track):
            logger.debug(
                f"[WEBRTC] Track received: {track.kind} for session {sessionid}")
            if track.kind == "audio":
                logger.debug(
                    f"[WEBRTC] Audio track received for session {sessionid}")
                # 将接收到的音频传递给ASR系统

                @track.on("ended")
                def on_ended():
                    logger.debug(
                        f"[WEBRTC] Audio track ended for session {sessionid}")

                # 处理接收到的音频帧
                async def process_audio_frames():
                    try:
                        while True:
                            frame = await track.recv()
                            # 将AudioFrame转换为numpy数组
                            if hasattr(frame, 'to_ndarray'):
                                audio_array = frame.to_ndarray()
                                # 转换为单声道和float32格式
                                if audio_array.ndim > 1:
                                    audio_array = audio_array[:, 0]
                                audio_array = audio_array.astype(np.float32)

                                # 传递给ASR系统
                                if hasattr(nerfreals[sessionid], 'add_asr_audio'):
                                    # 传递给LipReal的ASR缓冲区（用于文本识别）
                                    nerfreals[sessionid].add_asr_audio(
                                        audio_array)
                                elif hasattr(nerfreals[sessionid], 'lip_asr'):
                                    # 传递给LipASR用于口型驱动
                                    nerfreals[sessionid].lip_asr.put_audio_frame(
                                        audio_array, {})
                                elif hasattr(nerfreals[sessionid], 'asr'):
                                    # 传递给其他ASR实现（如MuseASR）
                                    nerfreals[sessionid].asr.put_audio_frame(
                                        audio_array, {})
                    except Exception as e:
                        logger.error(
                            f"[WEBRTC] Error processing audio frames: {str(e)}")

                # 启动音频处理任务
                asyncio.create_task(process_audio_frames())
            else:
                logger.warning(
                    f"[WEBRTC] Received non-audio track: {track.kind}")

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.debug(
                f"[WEBRTC] Connection state changed: {pc.connectionState} for session {sessionid}")

            # Proactively handle disconnection states
            if pc.connectionState in ("disconnected", "failed", "closed"):
                logger.warning(
                    f"[WEBRTC] Connection {pc.connectionState} for session {sessionid}")

                # Track stopping will be done by stop_worker_thread() below

                # 🆕 修复：先停止 HumanPlayer 的 worker 线程
                if sessionid in webrtc_players:
                    player = webrtc_players[sessionid]
                    try:
                        if hasattr(player, 'stop_worker_thread'):
                            logger.info(f"[WEBRTC] Stopping HumanPlayer worker thread for session {sessionid}")
                            player.stop_worker_thread()
                    except Exception as e:
                        logger.error(f"[WEBRTC] Error stopping worker thread: {str(e)}")
                    finally:
                        del webrtc_players[sessionid]

                # Close peer connection and cleanup
                try:
                    # 🆕 主动停止 nerfreal 的所有线程，防止资源泄漏
                    if sessionid in nerfreals:
                        nerfreal = nerfreals[sessionid]
                        try:
                            if hasattr(nerfreal, 'stop_all_threads'):
                                logger.info(f"[WEBRTC] Calling stop_all_threads for session {sessionid}")
                                nerfreal.stop_all_threads()
                        except Exception as e:
                            logger.error(f"[WEBRTC] Error stopping threads for session {sessionid}: {e}")

                    await pc.close()
                    pcs.discard(pc)
                    if sessionid in nerfreals:
                        del nerfreals[sessionid]
                    logger.debug(
                        f"[WEBRTC] Cleaned up {pc.connectionState} session {sessionid}")
                except Exception as e:
                    logger.error(
                        f"[WEBRTC] Error cleaning up {pc.connectionState} session: {str(e)}")

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.debug(
                f"[WEBRTC] ICE connection state changed: {pc.iceConnectionState} for session {sessionid}")
            if pc.iceConnectionState in ("disconnected", "failed", "closed"):
                logger.warning(
                    f"[WEBRTC] ICE connection {pc.iceConnectionState} for session {sessionid}")
                # 🆕 修复：先停止 HumanPlayer 的 worker 线程
                if sessionid in webrtc_players:
                    player = webrtc_players[sessionid]
                    try:
                        if hasattr(player, 'stop_worker_thread'):
                            logger.info(f"[WEBRTC] ICE: Stopping HumanPlayer worker thread for session {sessionid}")
                            player.stop_worker_thread()
                    except Exception as e:
                        logger.error(f"[WEBRTC] ICE: Error stopping worker thread: {str(e)}")
                    finally:
                        del webrtc_players[sessionid]

                # 🆕 主动停止 nerfreal 的所有线程，防止资源泄漏
                if sessionid in nerfreals:
                    nerfreal = nerfreals[sessionid]
                    try:
                        if hasattr(nerfreal, 'stop_all_threads'):
                            logger.info(f"[WEBRTC] ICE: Calling stop_all_threads for session {sessionid}")
                            nerfreal.stop_all_threads()
                    except Exception as e:
                        logger.error(f"[WEBRTC] ICE: Error stopping threads for session {sessionid}: {e}")

        # Create tracks
        try:
            logger.debug(
                f"[OFFER] Creating media tracks for session {sessionid}")
            player = HumanPlayer(nerfreals[sessionid])
            webrtc_players[sessionid] = player  # Store player reference for cleanup
            audio_sender = pc.addTrack(player.audio)
            video_sender = pc.addTrack(player.video)
            logger.debug(
                f"[OFFER] Media tracks created successfully for session {sessionid}")

        except Exception as e:
            logger.error(f"[OFFER] Failed to create media tracks: {str(e)}")
            try:
                await pc.close()
                pcs.discard(pc)
                if sessionid in nerfreals:
                    del nerfreals[sessionid]
            except:
                pass
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Failed to create media tracks: {str(e)}"}),
                status=500
            )

        # Configure codec preferences and bitrate
        try:
            capabilities = RTCRtpSender.getCapabilities("video")
            
            # Build codec preferences based on args.video_codec
            video_codec = args.video_codec
            preferences = []
            
            if video_codec == 'auto':
                # Auto: prefer VP9 > H264 > VP8 (best quality first)
                preferences = list(filter(lambda x: x.name == "VP9", capabilities.codecs))
                preferences += list(filter(lambda x: x.name == "H264", capabilities.codecs))
                preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
            elif video_codec == 'H264':
                preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
            elif video_codec == 'VP8':
                preferences = list(filter(lambda x: x.name == "VP8", capabilities.codecs))
            elif video_codec == 'VP9':
                preferences = list(filter(lambda x: x.name == "VP9", capabilities.codecs))
            
            # Always add rtx for retransmission
            preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
            
            # Get video transceiver (index 1, after audio)
            transceivers = pc.getTransceivers()
            video_transceiver = None
            for t in transceivers:
                if t.receiver.track and t.receiver.track.kind == 'video':
                    video_transceiver = t
                    break
            
            if video_transceiver:
                video_transceiver.setCodecPreferences(preferences)
                logger.debug(
                    f"[OFFER] Codec preferences configured: {[c.name for c in preferences[:3]]} for session {sessionid}")
                
                # Set bitrate parameters for all video senders
                video_bitrate_bps = args.video_bitrate * 1000  # Convert kbps to bps
                
                for sender in pc.getSenders():
                    if sender.track and sender.track.kind == 'video':
                        # Set encoding parameters
                        parameters = sender.getParameters()
                        if parameters and parameters.encodings:
                            # Update existing encoding parameters
                            for encoding in parameters.encodings:
                                encoding.maxBitrate = video_bitrate_bps
                                # Disable scale resolution down by default
                                encoding.scaleResolutionDownBy = 1
                            
                            sender.setParameters(parameters)
                            logger.info(
                                f"[OFFER] Video bitrate set to {args.video_bitrate} kbps for session {sessionid}")
                        else:
                            # Fallback: create new parameters
                            from aiortc.rtcrtpparameters import RTCRtpEncodingParameters
                            encodings = [RTCRtpEncodingParameters(
                                maxBitrate=video_bitrate_bps,
                                scaleResolutionDownBy=1
                            )]
                            parameters = RTCRtpParameters(encodings=encodings)
                            sender.setParameters(parameters)
                            logger.info(
                                f"[OFFER] Video bitrate set to {args.video_bitrate} kbps (new params) for session {sessionid}")
            else:
                logger.warning(f"[OFFER] No video transceiver found for session {sessionid}")
                
        except Exception as e:
            logger.warning(
                f"[OFFER] Failed to configure codec/bitrate: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())

        # Set remote description
        try:
            logger.debug(
                f"[OFFER] Setting remote description for session {sessionid}")
            await pc.setRemoteDescription(offer)
            logger.debug(
                f"[OFFER] Remote description set successfully for session {sessionid}")
        except Exception as e:
            logger.error(f"[OFFER] Failed to set remote description: {str(e)}")
            try:
                await pc.close()
                pcs.discard(pc)
                if sessionid in nerfreals:
                    del nerfreals[sessionid]
            except:
                pass
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Failed to set remote description: {str(e)}"}),
                status=500
            )

        # Create and set local description
        try:
            logger.debug(f"[OFFER] Creating answer for session {sessionid}")
            answer = await pc.createAnswer()
            logger.debug(
                f"[OFFER] Setting local description for session {sessionid}")
            await pc.setLocalDescription(answer)
            logger.debug(
                f"[OFFER] Local description set successfully for session {sessionid}")

        except Exception as e:
            logger.error(f"[OFFER] Failed to create/answer: {str(e)}")
            try:
                await pc.close()
                pcs.discard(pc)
                if sessionid in nerfreals:
                    del nerfreals[sessionid]
            except:
                pass
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Failed to create answer: {str(e)}"}),
                status=500
            )

        logger.debug(f"[OFFER] Session {sessionid} established successfully")
        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
                "sessionid": sessionid,
                "code": 0
            }),
        )

    except Exception as e:
        logger.exception(f"[OFFER] Unexpected error: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": f"Unexpected error: {str(e)}"}),
            status=500
        )


async def human(request):
    try:
        params = await safe_request_json(request)
        logger.debug(f"[HUMAN] Received human request: {params}")

        # Validate request parameters
        if not params:
            logger.error("[HUMAN] Empty request body")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Empty request body"}),
                status=400
            )

        # 验证 sessionid 格式（防止注入攻击）
        sessionid = params.get('sessionid')
        if sessionid is None:
            logger.error("[HUMAN] Missing sessionid in request")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Missing sessionid"}),
                status=400
            )

        # 验证 sessionid 是整数且在有效范围内
        if not isinstance(sessionid, int) or sessionid <= 0 or sessionid > 999999:
            logger.error(f"[HUMAN] Invalid sessionid format: {sessionid}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid sessionid format"}),
                status=400
            )

        if sessionid not in nerfreals:
            logger.error(f"[HUMAN] Session not found: {sessionid}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Session not found"}),
                status=404
            )

        # Check if nerfreal is properly initialized
        nerfreal = nerfreals.get(sessionid)
        if nerfreal is None:
            logger.error(
                f"[HUMAN] Nerfreal not initialized for session {sessionid}")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Nerfreal not initialized for session {sessionid}"}),
                status=500
            )

        # Handle interrupt
        if params.get('interrupt'):
            logger.debug(f"[HUMAN] Interrupting talk for session {sessionid}")
            try:
                nerfreal.flush_talk()
            except Exception as e:
                logger.error(f"[HUMAN] Failed to interrupt talk: {str(e)}")

        # Handle different message types
        msg_type = params.get('type', 'echo')
        text = params.get('text', '')

        if not text:
            logger.warning(f"[HUMAN] Empty text in request")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Empty text"}),
                status=400
            )

        logger.debug(
            f"[HUMAN] Processing {msg_type} message for session {sessionid}: {text}")

        if msg_type == 'echo':
            try:
                nerfreal.put_msg_txt(text)
                logger.debug(
                    f"[HUMAN] Echo message queued successfully for session {sessionid}")
            except Exception as e:
                logger.error(f"[HUMAN] Failed to queue echo message: {str(e)}")
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": -1, "msg": f"Failed to queue echo message: {str(e)}"}),
                    status=500
                )

        elif msg_type == 'chat':
            try:
                # Check if LLM is configured
                from llm import get_api_config
                api_key, base_url, model = get_api_config()
                if not api_key or not base_url:
                    logger.error("[HUMAN] LLM API not configured")
                    return web.Response(
                        content_type="application/json",
                        text=json.dumps(
                            {"code": -1, "msg": "LLM API not configured"}),
                        status=500
                    )

                # Run LLM response in executor
                logger.debug(
                    f"[HUMAN] Starting LLM response for session {sessionid}")
                # 传递 avatar_name 到 llm_response
                avatar_name = getattr(nerfreal, 'avatar_name', '小助手')
                asyncio.get_event_loop().run_in_executor(
                    None, llm_response, text, nerfreal, avatar_name)

                logger.debug(
                    f"[HUMAN] LLM response queued successfully for session {sessionid}")

            except Exception as e:
                logger.error(f"[HUMAN] Failed to queue LLM response: {str(e)}")
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": -1, "msg": f"Failed to process chat message: {str(e)}"}),
                    status=500
                )

        else:
            logger.warning(f"[HUMAN] Unknown message type: {msg_type}")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Unknown message type: {msg_type}"}),
                status=400
            )

        logger.debug(
            f"[HUMAN] Request processed successfully for session {sessionid}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "msg": "ok"}),
        )

    except Exception as e:
        logger.exception(f"[HUMAN] Unexpected error: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": f"Unexpected error: {str(e)}"}),
            status=500
        )


async def interrupt_talk(request):
    try:
        params = await safe_request_json(request)

        # 验证 sessionid 格式
        sessionid = params.get('sessionid')
        if sessionid is None or not isinstance(sessionid, int) or sessionid <= 0 or sessionid > 999999:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid sessionid"}),
                status=400
            )

        if sessionid not in nerfreals:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Session not found"}),
                status=404
            )

        nerfreals[sessionid].flush_talk()

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def humanaudio(request):
    try:
        form = await safe_request_post(request)

        # 验证 sessionid 格式
        sessionid_str = form.get('sessionid', '0')
        try:
            sessionid = int(sessionid_str)
        except (ValueError, TypeError):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid sessionid"}),
                status=400
            )

        if sessionid <= 0 or sessionid > 999999:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid sessionid"}),
                status=400
            )

        if sessionid not in nerfreals:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Session not found"}),
                status=404
            )

        fileobj = form["file"]
        filename = fileobj.filename

        # 检查文件大小（防止内存耗尽）
        content_length = request.content_length
        if content_length and content_length > MAX_AUDIO_SIZE:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"文件太大，最大允许 {MAX_AUDIO_SIZE // (1024*1024)}MB"}),
                status=413
            )

        # 读取文件，带大小限制
        filebytes = fileobj.file.read(MAX_AUDIO_SIZE)
        if len(filebytes) == MAX_AUDIO_SIZE:
            # 检查是否还有更多数据
            chunk = fileobj.file.read(1)
            if chunk:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"code": -1, "msg": f"文件太大，最大允许 {MAX_AUDIO_SIZE // (1024*1024)}MB"}),
                    status=413
                )

        nerfreals[sessionid].put_audio_file(filebytes)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def set_audiotype(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        nerfreals[sessionid].set_custom_state(
            params['audiotype'], params['reinit'])

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def record(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        if params['type'] == 'start_record':
            # nerfreals[sessionid].put_msg_txt(params['text'])
            nerfreals[sessionid].start_recording()
        elif params['type'] == 'end_record':
            nerfreals[sessionid].stop_recording()
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def is_speaking(request):
    params = await request.json()

    sessionid = params.get('sessionid', 0)
    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"code": 0, "data": nerfreals[sessionid].is_speaking()}
        ),
    )


async def speech_recognize(request):
    """使用腾讯 ASR 进行语音识别"""
    try:
        # 获取音频数据
        if request.content_type and 'multipart/form-data' in request.content_type:
            form = await request.post()
            fileobj = form.get("audio")
            if not fileobj:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"code": -1, "msg": "No audio file provided"}),
                    status=400
                )
            audio_bytes = fileobj.file.read()
        else:
            # JSON 请求，期望 base64 编码的音频
            data = await request.json()
            audio_base64 = data.get("audio")
            if not audio_base64:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"code": -1, "msg": "No audio data provided"}),
                    status=400
                )
            audio_bytes = base64.b64decode(audio_base64)

        # 使用腾讯 ASR 进行识别
        from tencentasr import TencentApiAsr

        # 创建临时配置对象
        class TempOpt:
            pass

        asr = TencentApiAsr(TempOpt())
        transcript = await asr.recognize(audio_bytes)

        logger.debug(f"[ASR] Tencent ASR result: {transcript}")

        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "code": 0,
                "data": {"text": transcript}
            }),
        )

    except Exception as e:
        logger.error(f"[ASR] Speech recognition error: {str(e)}", exc_info=True)
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )


# ──────────────────────────────────────────────
# Avatar API endpoint handlers
# ──────────────────────────────────────────────

async def avatars_list(request):
    """GET /avatars — 返回所有形象列表"""
    try:
        avatars = list_avatars()
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": avatars}, ensure_ascii=False)
        )
    except Exception as e:
        logger.exception(f"[AVATARS] list error: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )


async def avatar_get(request):
    """GET /avatars/{id} — 返回单个形象"""
    try:
        avatar_id = request.match_info.get("avatar_id", "")
        meta = get_avatar(avatar_id)
        if meta is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Avatar not found"}),
                status=404
            )
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": meta}, ensure_ascii=False)
        )
    except Exception as e:
        logger.exception(f"[AVATARS] get error: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )


async def avatar_create(request):
    """POST /avatars — 上传视频并触发形象生成"""
    try:
        reader = await request.multipart()

        avatar_id = None
        name = None
        tts_type = "doubao"  # 默认使用 doubao
        voice_id = "zh_female_wenroushunshun_mars_bigtts"  # 默认语音
        video_path = None

        async for field in reader:
            if field.name == "avatar_id":
                avatar_id = (await field.read()).decode("utf-8").strip()
            elif field.name == "name":
                name = (await field.read()).decode("utf-8").strip()
            elif field.name == "tts_type":
                tts_type = (await field.read()).decode("utf-8").strip()
            elif field.name == "voice_id":
                voice_id = (await field.read()).decode("utf-8").strip()
            elif field.name == "video":
                import uuid
                # Validate avatar_id format, regenerate if invalid
                if avatar_id:
                    from services.avatar_manager import validate_avatar_id
                    if not validate_avatar_id(avatar_id):
                        logger.warning(f"[AVATARS] Invalid avatar_id format: {avatar_id}, generating new one")
                        avatar_id = f"avatar_{uuid.uuid4().hex[:8]}"
                if not avatar_id:
                    avatar_id = f"avatar_{uuid.uuid4().hex[:8]}"
                uploads_dir = "data/uploads"
                os.makedirs(uploads_dir, exist_ok=True)
                filename = field.filename or f"{avatar_id}.mp4"
                video_path = os.path.join(uploads_dir, f"{avatar_id}_{filename}")
                with open(video_path, "wb") as f:
                    while True:
                        chunk = await field.read_chunk(65536)
                        if not chunk:
                            break
                        f.write(chunk)

        if not avatar_id or not name:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "avatar_id and name are required"}),
                status=400
            )
        if not video_path or not os.path.exists(video_path):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Video file is required"}),
                status=400
            )

        # 在后台异步生成（不阻塞响应）
        async def _run_gen():
            try:
                await generate_avatar_async(
                    avatar_id, video_path, name, tts_type, voice_id)
                try:
                    os.remove(video_path)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"[AVATAR_GEN] Generation failed for {avatar_id}: {e}")

        asyncio.create_task(_run_gen())

        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "code": 0,
                "msg": "Generation started",
                "data": {"avatar_id": avatar_id, "status": "creating"}
            }, ensure_ascii=False)
        )
    except Exception as e:
        logger.exception(f"[AVATARS] create error: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )


async def avatar_update(request):
    """PUT /avatars/{id} — 更新形象元数据（名称/语音绑定）"""
    try:
        avatar_id = request.match_info.get("avatar_id", "")
        params = await request.json()
        updated = update_avatar(avatar_id, params)
        if updated is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Avatar not found"}),
                status=404
            )
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "data": updated}, ensure_ascii=False)
        )
    except Exception as e:
        logger.exception(f"[AVATARS] update error: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )


async def avatar_delete(request):
    """DELETE /avatars/{id} — 删除形象"""
    try:
        avatar_id = request.match_info.get("avatar_id", "")
        ok = delete_avatar(avatar_id)
        if not ok:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Avatar not found"}),
                status=404
            )
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "msg": "Deleted"})
        )
    except Exception as e:
        logger.exception(f"[AVATARS] delete error: {e}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500
        )




async def preview_voice_tts(request):
    """
    生成音色试听音频
    Returns: Audio data (audio/mpeg)
    """
    try:
        params = await request.json()
        voice_id = params.get('voice_id')

        if not voice_id:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "voice_id is required"}),
                status=400
            )

        # Validate voice_id format
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', voice_id):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid voice_id format"}),
                status=400
            )

        # Call Doubao TTS service to generate preview audio
        from tts_service import generate_preview_audio

        audio_data = await generate_preview_audio(
            text="你好，我是数字人。",  # Fixed preview text
            voice_id=voice_id
        )

        if not audio_data:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Failed to generate audio"}),
                status=500
            )

        return web.Response(
            body=audio_data,
            content_type='audio/mpeg'
        )

    except Exception as e:
        logger.error(f"[PREVIEW] Voice preview failed: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": f"Preview failed: {str(e)}"}),
            status=500
        )
async def on_startup(app):
    """应用启动时初始化"""
    logger.info("[启动] 应用启动初始化...")
    
    # 存储监控任务引用到 app 对象，防止被垃圾回收
    app['monitor_task'] = asyncio.create_task(monitor_task())
    logger.info("[启动] 监控任务已创建")


async def on_shutdown(app):
    """应用关闭时清理资源"""
    logger.info("[SHUTDOWN] 应用关闭...")
    
    # 取消监控任务
    if 'monitor_task' in app and app['monitor_task'] and not app['monitor_task'].done():
        app['monitor_task'].cancel()
        try:
            await app['monitor_task']
        except asyncio.CancelledError:
            logger.info("[SHUTDOWN] 监控任务已取消")
    
    # 清理所有会话
    for sessionid in list(nerfreals.keys()):
        try:
            if nerfreals[sessionid] is not None and hasattr(nerfreals[sessionid], 'stop_all_threads'):
                nerfreals[sessionid].stop_all_threads()
                logger.info(f"[SHUTDOWN] 已清理会话 {sessionid}")
        except Exception as e:
            logger.error(f"[SHUTDOWN] 清理会话 {sessionid} 失败: {e}")
    
    nerfreals.clear()
    
    # 关闭对等连接
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros, return_exceptions=True)
    pcs.clear()
    
    logger.info("[SHUTDOWN] 应用关闭完成")


async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.info(f'Error: {e}')


async def run(push_url, sessionid, avatar_id):
    nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, avatar_id)


    nerfreals[sessionid] = nerfreal

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState in ("disconnected", "failed", "closed"):
            # 🆕 修复：先停止 HumanPlayer 的 worker 线程
            if sessionid in webrtc_players:
                player = webrtc_players[sessionid]
                try:
                    if hasattr(player, 'stop_worker_thread'):
                        logger.info(f"[WEBRTC] Human: Stopping HumanPlayer worker thread for session {sessionid}")
                        player.stop_worker_thread()
                except Exception as e:
                    logger.error(f"[WEBRTC] Human: Error stopping worker thread: {str(e)}")
                finally:
                    del webrtc_players[sessionid]

            # 🆕 主动停止 nerfreal 的所有线程，防止资源泄漏
            if sessionid in nerfreals:
                nerfreal = nerfreals[sessionid]
                try:
                    if hasattr(nerfreal, 'stop_all_threads'):
                        logger.info(f"[WEBRTC] Human: Calling stop_all_threads for session {sessionid}")
                        nerfreal.stop_all_threads()
                except Exception as e:
                    logger.error(f"[WEBRTC] Human: Error stopping threads for session {sessionid}: {e}")

            await pc.close()
            pcs.discard(pc)
            if sessionid in nerfreals:
                del nerfreals[sessionid]

    player = HumanPlayer(nerfreals[sessionid])
    webrtc_players[sessionid] = player  # Store player reference for cleanup
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    if answer is not None:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type='answer'))
    else:
        logger.warning(f"[RUN] Failed to get SDP answer from {push_url}, session {sessionid} will wait for client connection")
##########################################
# os.environ['MKL_SERVICE_FORCE_INTEL'] = '1'
# os.environ['MULTIPROCESSING_METHOD'] = 'forkserver'
if __name__ == '__main__':
    # 在启动前进行服务健康检查
    try:
        from service_health_check import ServiceHealthChecker
        checker = ServiceHealthChecker()
        health_check_passed = checker.check_all()

        if not health_check_passed:
            logger.error("=" * 60)
            logger.error("❌ 健康检查失败，服务不可用")
            logger.error("请检查配置文件和网络连接后再启动")
            logger.error("=" * 60)
            sys.exit(1)
    except ImportError:
        logger.warning("⚠️  无法导入健康检查模块，跳过健康检查")
    except Exception as e:
        logger.warning(f"⚠️  健康检查失败: {e}，继续启动...")

    mp.set_start_method('spawn')
    parser = argparse.ArgumentParser()

    # audio FPS
    parser.add_argument('--fps', type=int, default=50,
                        help="audio fps,must be 50")
    # sliding window left-middle-right length (unit: 20ms)
    parser.add_argument('-l', type=int, default=10)
    parser.add_argument('-m', type=int, default=8)
    parser.add_argument('-r', type=int, default=10)

    parser.add_argument('--W', type=int, default=768, help="GUI width")
    parser.add_argument('--H', type=int, default=768, help="GUI height")
    
    # WebRTC video bitrate control
    parser.add_argument('--video_bitrate', type=int, default=8000,
                        help="Video bitrate in kbps (default: 8000, recommended: 5000-10000)")
    parser.add_argument('--video_codec', type=str, default='auto',
                        choices=['auto', 'H264', 'VP8', 'VP9'],
                        help="Video codec preference (default: auto)")

    # musetalk opt
    parser.add_argument('--avatar_id', type=str, default='wav2lip256_avatar1',
                        help="define which avatar in data/avatars")
    # parser.add_argument('--bbox_shift', type=int, default=5)
    parser.add_argument('--batch_size', type=int,
                        default=16, help="infer batch")

    parser.add_argument('--customvideo_config', type=str,
                        default='', help="custom action json")

    # xtts gpt-sovits cosyvoice fishtts tencent doubao indextts2 azuretts edgetts
    parser.add_argument('--tts', type=str, default=os.getenv('TTS_TYPE', 'edgetts'),
                        help="tts service type (from env TTS_TYPE)")
    parser.add_argument('--REF_FILE', type=str, default="zh_female_xiaohe_uranus_bigtts",
                        help="参考文件名或语音模型ID，对于豆包TTS使用voice_id，如zh_female_xiaohe_uranus_bigtts")
    parser.add_argument('--REF_TEXT', type=str, default=None)
    # http://localhost:9000
    parser.add_argument('--TTS_SERVER', type=str,
                        default='http://127.0.0.1:9880')
    # parser.add_argument('--CHARACTER', type=str, default='test')
    # parser.add_argument('--EMOTION', type=str, default='default')

    # musetalk wav2lip ultralight
    parser.add_argument('--model', type=str, default='wav2lip')

    # webrtc rtcpush virtualcam
    parser.add_argument('--transport', type=str, default='webrtc')
    # rtmp://localhost/live/livestream
    parser.add_argument('--push_url', type=str,
                        default='http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream')

    parser.add_argument('--max_session', type=int,
                        default=1)  # multi session count
    parser.add_argument('--listenport', type=int,
                        default=8010, help="web listen port")

    # ASR配置 (通过环境变量读取)
    parser.add_argument('--asr', type=str, default=None,
                        help="ASR service type (from env ASR_TYPE)")

    args = parser.parse_args()
    opt = args
    # app.config.from_object(opt)
    # print(app.config)
    opt.customopt = []
    if opt.customvideo_config != '':
        with open(opt.customvideo_config, 'r') as file:
            opt.customopt = json.load(file)

    # if opt.model == 'ernerf':
    #     from nerfreal import NeRFReal,load_model,load_avatar
    #     model = load_model(opt)
    #     avatar = load_avatar(opt)
    if opt.model == 'musetalk':
        from musereal import MuseReal, load_avatar, load_model, warm_up
        logger.info(opt)
        model = load_model()
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model)
    elif opt.model == 'wav2lip':
        from lipreal import LipReal, load_avatar, load_model, warm_up
        logger.info(opt)
        model_path = "./models/wav2lip384.pth"
        if not os.path.exists(model_path):
            logger.error(f"模型文件不存在: {model_path}")
            sys.exit(1)
        model = load_model(model_path)
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model, 384)
    elif opt.model == 'ultralight':
        from lightreal import LightReal, load_avatar, load_model, warm_up
        logger.info(opt)
        model = load_model(opt)
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, avatar, 160)
    if opt.transport == 'virtualcam':
        thread_quit = Event()
        nerfreals[0] = build_nerfreal(0, opt.avatar_id)
        rendthrd = Thread(target=nerfreals[0].render, args=(thread_quit,))
        rendthrd.start()

    #############################################################################
    # 初始化安全组件
    global rate_limiter, nerfreals_lock
    rate_limiter = RateLimiter(max_requests=60, window=60)
    nerfreals_lock = asyncio.Lock()
    logger.info("[安全] 频率限制器和会话锁已初始化")

    # 创建应用并配置超时中间件
    appasync = web.Application(
        client_max_size=1024**2*100,
        middlewares=[timeout_middleware_factory]  # 全局超时中间件
    )
    appasync.on_startup.append(on_startup)
    appasync.on_shutdown.append(on_shutdown)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/humanaudio", humanaudio)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/record", record)
    appasync.router.add_post("/interrupt_talk", interrupt_talk)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_post("/speech_recognize", speech_recognize)

    # Avatar 管理路由
    appasync.router.add_get("/avatars", avatars_list)
    appasync.router.add_post("/avatars", avatar_create)
    appasync.router.add_get("/avatars/{avatar_id}", avatar_get)
    appasync.router.add_put("/avatars/{avatar_id}", avatar_update)
    appasync.router.add_delete("/avatars/{avatar_id}", avatar_delete)
    appasync.router.add_post('/preview_voice', preview_voice_tts)
    # Avatar 静态资源（图片等）
    appasync.router.add_static("/avatars/", path="data/avatars", name="avatar_static")


    appasync.router.add_static('/', path='frontend/web')

    # ========== 启动监控任务 ==========
    # 监控任务通过 on_startup 处理器启动
    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
        loop.run_until_complete(site.start())
        # 禁用自动创建会话的预热逻辑，避免占用会话配额
        # if opt.transport == 'rtcpush':
        #     for k in range(opt.max_session):
        #         push_url = opt.push_url
        #         if k != 0:
        #             push_url = opt.push_url+str(k)
        #         loop.run_until_complete(run(push_url, k, opt.avatar_id))
        logger.info(f"[SERVER] Ready to accept up to {opt.max_session} client connections")
        loop.run_forever()
    # Thread(target=run_server, args=(web.AppRunner(appasync),)).start()
    run_server(web.AppRunner(appasync))

    # app.on_shutdown.append(on_shutdown)
    # app.router.add_post("/offer", offer)

    # print('start websocket server')
    # server = pywsgi.WSGIServer(('0.0.0.0', 8000), app, handler_class=WebSocketHandler)
    # server.serve_forever()
