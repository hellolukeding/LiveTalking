#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速启动脚本 - 修复导入路径版本
"""

import argparse
import json
import os
import sys

import torch
import torch.multiprocessing as mp

# 将项目根目录添加到Python路径
project_root = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

# 添加 services 目录到路径
services_path = os.path.join(project_root, 'src', 'services')
if services_path not in sys.path:
    sys.path.insert(0, services_path)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, os.path.join(project_root, 'src', 'core'))
sys.path.insert(0, os.path.join(project_root, 'src', 'llm'))
sys.path.insert(0, os.path.join(project_root, 'src', 'utils'))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入日志
from utils.logger import logger


def setup_config():
    """设置配置，使用可用的服务"""

    # 创建配置对象
    class Config:
        def __init__(self):
            # 基础配置
            self.fps = 30  # 音频FPS
            self.l = 10    # 左窗口长度
            self.m = 8     # 中窗口长度
            self.r = 10    # 右窗口长度
            self.W = 450   # GUI宽度
            self.H = 450   # GUI高度

            # 模型配置
            self.model = 'wav2lip'  # 使用wav2lip模型
            self.avatar_id = 'wav2lip384_avatar1'
            self.batch_size = 16

            # TTS配置 - 从环境变量读取，如果没有则默认使用Edge TTS（免费）
            tts_type = os.getenv('TTS_TYPE', 'edge')
            self.tts = tts_type

            # 根据TTS类型设置REF_FILE
            if tts_type == 'doubao':
                self.REF_FILE = os.getenv(
                    'DOUBAO_VOICE_ID', 'zh_female_xiaohe_uranus_bigtts')
            elif tts_type == 'tencent':
                self.REF_FILE = os.getenv('TENCENT_VOICE_TYPE', '1001')
            elif tts_type == 'azure':
                self.REF_FILE = os.getenv(
                    'AZURE_VOICE_NAME', 'zh-CN-XiaoxiaoNeural')
            else:  # edge tts
                self.REF_FILE = os.getenv(
                    'EDGE_TTS_VOICE', 'zh-CN-YunxiNeural')

            self.REF_TEXT = None
            self.TTS_SERVER = 'http://127.0.0.1:9880'

            # ASR配置 - 从环境变量读取，默认使用Lip ASR（本地可用）
            self.asr = os.getenv('ASR_TYPE', 'lip')

            # 传输配置
            self.transport = 'rtmp'  # 使用 rtmp 推流模式
            self.push_url = 'rtmp://localhost/live/livestream'  # SRS RTMP 推流地址
            self.max_session = 1
            # 使用环境变量中的端口，如果没有则使用8011（避免8010被占用）
            self.listenport = int(os.getenv('LISTEN_PORT', 8011))

            # 会话ID
            self.sessionid = 0
            self.customopt = []

            # 检查并设置环境变量
            self.update_from_env()

        def update_from_env(self):
            """从环境变量更新配置"""
            # TTS类型 - 已在__init__中处理，这里仅更新其他配置
            # ASR类型
            asr_type = os.getenv('ASR_TYPE', 'lip')
            self.asr = asr_type

            # 其他配置
            self.fps = int(os.getenv('FPS', 30))
            self.max_session = int(os.getenv('MAX_SESSION', 1))
            self.listenport = int(os.getenv('LISTEN_PORT', 8010))
            if self.model == 'wav2lip' and self.fps != 50:
                logger.warning(f"[Wav2Lip] FPS={self.fps} is unsafe for audio; forcing to 50")
                self.fps = 50

    config = Config()
    return config


def build_nerfreal(opt, model, avatar):
    """构建nerfreal实例"""
    if opt.model == 'wav2lip':
        from lipreal import LipReal
        nerfreal = LipReal(opt, model, avatar)
    elif opt.model == 'musetalk':
        from musereal import MuseReal
        nerfreal = MuseReal(opt, model, avatar)
    elif opt.model == 'ultralight':
        from lightreal import LightReal
        nerfreal = LightReal(opt, model, avatar)
    else:
        raise ValueError(f"不支持的模型类型: {opt.model}")

    return nerfreal


def load_models(opt):
    """加载模型"""
    logger.debug("正在加载模型...")

    if opt.model == 'musetalk':
        from musereal import MuseReal, load_avatar, load_model, warm_up
        model = load_model()
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model)
    elif opt.model == 'wav2lip':
        from lipreal import LipReal, load_avatar, load_model, warm_up
        model = load_model("./models/wav2lip384.pth")
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model, 384)
    elif opt.model == 'ultralight':
        from lightreal import LightReal, load_avatar, load_model, warm_up
        model = load_model(opt)
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, avatar, 160)

    logger.debug("模型加载完成")
    return model, avatar


def main():
    """主函数"""
    print("=" * 70)
    print("🚀 LiveTalking 快速启动 (修复版)")
    print("=" * 70)
    print()

    # 显示配置信息
    opt = setup_config()  # 先获取配置用于显示
    tts_name = {
        'doubao': '豆包TTS',
        'edgetts': 'Edge TTS (免费)',
        'tencent': '腾讯TTS',
        'azure': 'Azure TTS',
        'gpt-sovits': 'GPT-SoVITS',
        'xtts': 'XTTS',
        'cosyvoice': 'CosyVoice',
        'fishtts': 'FishTTS',
        'indextts2': 'IndexTTS2'
    }.get(opt.tts, opt.tts)

    asr_name = {
        'lip': 'Lip ASR (本地)',
        'tencent': '腾讯ASR',
        'funasr': 'FunASR',
        'huber': 'Huber ASR'
    }.get(opt.asr, opt.asr)

    print("📋 使用配置:")
    print(f"  TTS: {tts_name}")
    print(f"  ASR: {asr_name}")
    print("  模型: Wav2Lip")
    print(f"  端口: {opt.listenport}")
    print()

    # 确认继续（在容器/非交互环境中自动继续，或设置 NO_PROMPT=1 跳过问询）
    print("⚠️  注意: 此模式跳过健康检查，使用推荐配置")
    print()
    need_prompt = sys.stdin.isatty() and os.getenv("NO_PROMPT", "0") != "1"
    if need_prompt:
        response = input("是否继续? (y/n): ")
        if response.lower() != 'y':
            print("已取消")
            return
    else:
        print("非交互模式或 NO_PROMPT=1，自动继续")

    print()

    # 设置配置
    opt = setup_config()

    # 设置多进程启动方法
    mp.set_start_method('spawn')

    # 加载模型
    try:
        model, avatar = load_models(opt)
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        print("请确保模型文件存在于 models/ 目录")
        return

    # 启动Web服务器
    print("\n📡 启动Web服务器...")

    # 导入必要的模块
    import asyncio

    import aiohttp
    import aiohttp_cors
    from aiohttp import web
    from aiortc import (RTCConfiguration, RTCIceServer, RTCPeerConnection,
                        RTCSessionDescription)
    from aiortc.rtcrtpsender import RTCRtpSender
    from basereal import BaseReal
    from webrtc import HumanPlayer

    # 全局变量
    nerfreals = {}
    pcs = set()

    # 导入 avatar 服务
    from avatar_manager import (
        list_avatars, get_avatar, update_avatar, delete_avatar,
        generate_avatar_async
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
            tts_type = "edge"
            voice_id = "zh-CN-XiaoxiaoNeural"
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
                    # 保存上传的视频到临时目录
                    import uuid
                    if not avatar_id:
                        avatar_id = f"avatar_{uuid.uuid4().hex[:8]}"
                    uploads_dir = os.path.join(project_root, "data", "uploads")
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
                    # 生成完成后删除上传的临时视频
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
            logger.exception(f"[AVATAR_CREATE] error: {e}")
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
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": str(e)}),
                status=500
            )

    # ──────────────────────────────────────────────
    # 从app.py复制的关键函数
    # ──────────────────────────────────────────────
    def randN(N):
        import random
        min_val = pow(10, N - 1)
        max_val = pow(10, N)
        return random.randint(min_val, max_val - 1)

    async def offer(request):
        try:
            params = await request.json()
            logger.debug(f"[OFFER] Received offer request: {params}")

            if not params or 'sdp' not in params or 'type' not in params:
                return web.Response(
                    content_type="application/json",
                    text='{"code": -1, "msg": "Invalid request"}',
                    status=400
                )

            offer = RTCSessionDescription(
                sdp=params["sdp"], type=params["type"])

            if len(nerfreals) >= opt.max_session:
                return web.Response(
                    content_type="application/json",
                    text='{"code": -1, "msg": "reach max session"}',
                    status=429
                )

            sessionid = randN(6)
            opt.sessionid = sessionid

            # 构建nerfreal
            nerfreal = build_nerfreal(opt, model, avatar)
            nerfreals[sessionid] = nerfreal

            # WebRTC连接
            ice_server = RTCIceServer(urls='stun:stun.l.google.com:19302')
            pc = RTCPeerConnection(
                configuration=RTCConfiguration(iceServers=[ice_server]))
            pcs.add(pc)

            @pc.on("datachannel")
            def on_datachannel(channel):
                nerfreals[sessionid].datachannel = channel
                nerfreals[sessionid].loop = asyncio.get_event_loop()

            @pc.on("track")
            def on_track(track):
                if track.kind == "audio":
                    @track.on("ended")
                    def on_ended():
                        pass

                    async def process_audio_frames():
                        try:
                            while True:
                                frame = await track.recv()
                                if hasattr(frame, 'to_ndarray'):
                                    audio_array = frame.to_ndarray()
                                    if audio_array.ndim > 1:
                                        audio_array = audio_array[:, 0]
                                    audio_array = audio_array.astype('float32')

                                    if hasattr(nerfreals[sessionid], 'add_asr_audio'):
                                        nerfreals[sessionid].add_asr_audio(
                                            audio_array)
                                    elif hasattr(nerfreals[sessionid], 'lip_asr'):
                                        nerfreals[sessionid].lip_asr.put_audio_frame(
                                            audio_array, {})
                                    elif hasattr(nerfreals[sessionid], 'asr'):
                                        nerfreals[sessionid].asr.put_audio_frame(
                                            audio_array, {})
                        except Exception as e:
                            logger.error(f"Audio processing error: {e}")

                    asyncio.create_task(process_audio_frames())

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(
                    f"[WEBRTC] Session {sessionid} connection state: {pc.connectionState}")
                if pc.connectionState == "failed":
                    logger.error(
                        f"[WEBRTC] Session {sessionid} connection failed, cleaning up...")
                    try:
                        await pc.close()
                    except Exception as e:
                        logger.error(f"[WEBRTC] Error closing connection: {e}")
                    pcs.discard(pc)
                    if sessionid in nerfreals:
                        try:
                            nerfreal = nerfreals[sessionid]
                            # 关闭TTS连接池
                            if hasattr(nerfreal, 'tts') and hasattr(nerfreal.tts, 'shutdown'):
                                nerfreal.tts.shutdown()
                            del nerfreals[sessionid]
                            logger.info(
                                f"[WEBRTC] Session {sessionid} cleaned up")
                        except Exception as e:
                            logger.error(
                                f"[WEBRTC] Error cleaning up session {sessionid}: {e}")
                elif pc.connectionState == "closed":
                    logger.info(
                        f"[WEBRTC] Session {sessionid} connection closed")
                    pcs.discard(pc)
                    if sessionid in nerfreals:
                        try:
                            nerfreal = nerfreals[sessionid]
                            # 关闭TTS连接池
                            if hasattr(nerfreal, 'tts') and hasattr(nerfreal.tts, 'shutdown'):
                                nerfreal.tts.shutdown()
                            del nerfreals[sessionid]
                            logger.info(
                                f"[WEBRTC] Session {sessionid} cleaned up")
                        except Exception as e:
                            logger.error(
                                f"[WEBRTC] Error cleaning up session {sessionid}: {e}")
                elif pc.connectionState == "disconnected":
                    logger.warning(
                        f"[WEBRTC] Session {sessionid} connection disconnected")
                elif pc.connectionState == "connecting":
                    logger.info(
                        f"[WEBRTC] Session {sessionid} connection connecting...")
                elif pc.connectionState == "connected":
                    logger.info(
                        f"[WEBRTC] Session {sessionid} connection connected successfully")

            # 创建媒体轨道
            player = HumanPlayer(nerfreals[sessionid])
            pc.addTrack(player.audio)
            pc.addTrack(player.video)

            # 设置描述
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            return web.Response(
                content_type="application/json",
                text=json.dumps({
                    "sdp": pc.localDescription.sdp,
                    "type": pc.localDescription.type,
                    "sessionid": sessionid,
                    "code": 0
                })
            )

        except Exception as e:
            logger.exception(f"Offer error: {e}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": str(e)}),
                status=500
            )

    async def human(request):
        try:
            params = await request.json()
            sessionid = params.get('sessionid', 0)

            if sessionid not in nerfreals:
                return web.Response(
                    content_type="application/json",
                    text='{"code": -1, "msg": "Invalid session"}',
                    status=400
                )

            nerfreal = nerfreals[sessionid]

            if params.get('interrupt'):
                nerfreal.flush_talk()

            msg_type = params.get('type', 'echo')
            text = params.get('text', '')

            if not text:
                return web.Response(
                    content_type="application/json",
                    text='{"code": -1, "msg": "Empty text"}',
                    status=400
                )

            if msg_type == 'echo':
                nerfreal.put_msg_txt(text)
            elif msg_type == 'chat':
                from llm import llm_response
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, llm_response, text, nerfreal)

            return web.Response(
                content_type="application/json",
                text='{"code": 0, "msg": "ok"}'
            )

        except Exception as e:
            logger.exception(f"Human error: {e}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": str(e)}),
                status=500
            )

    async def on_shutdown(app):
        coros = [pc.close() for pc in pcs]
        await asyncio.gather(*coros)
        pcs.clear()

    # 创建应用
    appasync = web.Application(client_max_size=1024**2*100)
    appasync.on_shutdown.append(on_shutdown)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)

    # Avatar 管理路由
    appasync.router.add_get("/avatars", avatars_list)
    appasync.router.add_post("/avatars", avatar_create)
    appasync.router.add_get("/avatars/{avatar_id}", avatar_get)
    appasync.router.add_put("/avatars/{avatar_id}", avatar_update)
    appasync.router.add_delete("/avatars/{avatar_id}", avatar_delete)

    # 设置web目录路径 - 从项目根目录查找
    web_path = os.path.join(project_root, 'frontend', 'web')
    if not os.path.exists(web_path):
        web_path = os.path.join(project_root, 'web')  # 兼容旧路径

    if os.path.exists(web_path):
        appasync.router.add_static('/', path=web_path)
        print(f"✅ Web目录: {web_path}")
    else:
        print(f"⚠️  Web目录未找到: {web_path}")

    # 配置CORS
    cors = aiohttp_cors.setup(appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    for route in list(appasync.router.routes()):
        cors.add(route)

    # 启动服务器
    async def run_server():
        runner = web.AppRunner(appasync)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
        await site.start()

        print(f"✅ 服务器启动成功!")
        print(f"📊 访问地址: http://<serverip>:{opt.listenport}/webrtcapi.html")
        print(f"📱 推荐前端: http://<serverip>:{opt.listenport}/dashboard.html")
        print()
        print("🎉 LiveTalking 已启动，可以开始使用了!")
        print("=" * 70)

        # 保持运行
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\n👋 正在关闭...")
    except Exception as e:
        print(f"❌ 服务器错误: {e}")


if __name__ == "__main__":
    main()
