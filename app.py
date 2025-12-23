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
import asyncio
import base64
import gc
import json
import random
import re
import shutil
from threading import Event, Thread
from typing import Dict

import aiohttp
import aiohttp_cors
import numpy as np
import torch
import torch.multiprocessing as mp
from aiohttp import web
from aiortc import (RTCConfiguration, RTCIceServer, RTCPeerConnection,
                    RTCSessionDescription)
from aiortc.rtcrtpsender import RTCRtpSender
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_sockets import Sockets

from basereal import BaseReal
from llm import llm_response
from logger import logger
from webrtc import HumanPlayer

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


def randN(N) -> int:
    '''生成长度为 N的随机数 '''
    min = pow(10, N - 1)
    max = pow(10, N)
    return random.randint(min, max - 1)


def build_nerfreal(sessionid: int) -> BaseReal:
    opt.sessionid = sessionid
    if opt.model == 'wav2lip':
        from lipreal import LipReal
        nerfreal = LipReal(opt, model, avatar)
    elif opt.model == 'musetalk':
        from musereal import MuseReal
        nerfreal = MuseReal(opt, model, avatar)
    # elif opt.model == 'ernerf':
    #     from nerfreal import NeRFReal
    #     nerfreal = NeRFReal(opt,model,avatar)
    elif opt.model == 'ultralight':
        from lightreal import LightReal
        nerfreal = LightReal(opt, model, avatar)
    return nerfreal

# @app.route('/offer', methods=['POST'])


async def offer(request):
    try:
        params = await request.json()
        logger.info(f"[OFFER] Received offer request: {params}")

        if not params or 'sdp' not in params or 'type' not in params:
            logger.error("[OFFER] Invalid request parameters")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": "Invalid request: missing sdp or type"}),
                status=400
            )

        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        logger.info(
            f"[OFFER] Created RTCSessionDescription: type={params['type']}")

        # Check session limit
        if len(nerfreals) >= opt.max_session:
            logger.warning(
                f"[OFFER] Max session limit reached: {len(nerfreals)} >= {opt.max_session}")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "reach max session"}),
                status=429
            )

        sessionid = randN(6)
        logger.info(f"[OFFER] Generating session ID: {sessionid}")

        # Initialize session with error handling
        try:
            nerfreals[sessionid] = None
            logger.info(f"[OFFER] Building nerfreal for session {sessionid}")

            # Build nerfreal in executor to avoid blocking
            nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)

            if nerfreal is None:
                raise RuntimeError("Failed to build nerfreal instance")

            nerfreals[sessionid] = nerfreal
            logger.info(
                f"[OFFER] Nerfreal built successfully for session {sessionid}")

        except Exception as e:
            logger.error(f"[OFFER] Failed to build nerfreal: {str(e)}")
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
            ice_server = RTCIceServer(urls='stun:stun.l.google.com:19302')
            pc = RTCPeerConnection(
                configuration=RTCConfiguration(iceServers=[ice_server]))
            pcs.add(pc)
            logger.info(
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
            logger.info(
                f"[WEBRTC] Data channel created: {channel.label} for session {sessionid}")
            try:
                nerfreals[sessionid].datachannel = channel
                nerfreals[sessionid].loop = asyncio.get_event_loop()
                logger.info(
                    f"[WEBRTC] Data channel initialized for session {sessionid}")
            except Exception as e:
                logger.error(
                    f"[WEBRTC] Failed to initialize data channel: {str(e)}")

        @pc.on("track")
        def on_track(track):
            logger.info(
                f"[WEBRTC] Track received: {track.kind} for session {sessionid}")
            if track.kind == "audio":
                logger.info(
                    f"[WEBRTC] Audio track received for session {sessionid}")
                # 将接收到的音频传递给ASR系统

                @track.on("ended")
                def on_ended():
                    logger.info(
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
            logger.info(
                f"[WEBRTC] Connection state changed: {pc.connectionState} for session {sessionid}")
            if pc.connectionState == "failed":
                logger.error(
                    f"[WEBRTC] Connection failed for session {sessionid}")
                try:
                    await pc.close()
                    pcs.discard(pc)
                    if sessionid in nerfreals:
                        del nerfreals[sessionid]
                    logger.info(
                        f"[WEBRTC] Cleaned up failed session {sessionid}")
                except Exception as e:
                    logger.error(
                        f"[WEBRTC] Error cleaning up failed session: {str(e)}")
            elif pc.connectionState == "closed":
                logger.info(
                    f"[WEBRTC] Connection closed for session {sessionid}")
                try:
                    pcs.discard(pc)
                    if sessionid in nerfreals:
                        del nerfreals[sessionid]
                    logger.info(
                        f"[WEBRTC] Cleaned up closed session {sessionid}")
                except Exception as e:
                    logger.error(
                        f"[WEBRTC] Error cleaning up closed session: {str(e)}")

        # Create tracks
        try:
            logger.info(
                f"[OFFER] Creating media tracks for session {sessionid}")
            player = HumanPlayer(nerfreals[sessionid])
            audio_sender = pc.addTrack(player.audio)
            video_sender = pc.addTrack(player.video)
            logger.info(
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

        # Configure codec preferences
        try:
            capabilities = RTCRtpSender.getCapabilities("video")
            preferences = list(
                filter(lambda x: x.name == "H264", capabilities.codecs))
            preferences += list(filter(lambda x: x.name ==
                                "VP8", capabilities.codecs))
            preferences += list(filter(lambda x: x.name ==
                                "rtx", capabilities.codecs))
            transceiver = pc.getTransceivers()[1]
            transceiver.setCodecPreferences(preferences)
            logger.info(
                f"[OFFER] Codec preferences configured for session {sessionid}")
        except Exception as e:
            logger.warning(
                f"[OFFER] Failed to configure codec preferences: {str(e)}")

        # Set remote description
        try:
            logger.info(
                f"[OFFER] Setting remote description for session {sessionid}")
            await pc.setRemoteDescription(offer)
            logger.info(
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
            logger.info(f"[OFFER] Creating answer for session {sessionid}")
            answer = await pc.createAnswer()
            logger.info(
                f"[OFFER] Setting local description for session {sessionid}")
            await pc.setLocalDescription(answer)
            logger.info(
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

        logger.info(f"[OFFER] Session {sessionid} established successfully")
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
        params = await request.json()
        logger.info(f"[HUMAN] Received human request: {params}")

        # Validate request parameters
        if not params:
            logger.error("[HUMAN] Empty request body")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Empty request body"}),
                status=400
            )

        sessionid = params.get('sessionid', 0)
        if not sessionid or sessionid not in nerfreals:
            logger.error(f"[HUMAN] Invalid session ID: {sessionid}")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"Invalid or missing session ID: {sessionid}"}),
                status=400
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
            logger.info(f"[HUMAN] Interrupting talk for session {sessionid}")
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

        logger.info(
            f"[HUMAN] Processing {msg_type} message for session {sessionid}: {text}")

        if msg_type == 'echo':
            try:
                nerfreal.put_msg_txt(text)
                logger.info(
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
                logger.info(
                    f"[HUMAN] Starting LLM response for session {sessionid}")
                asyncio.get_event_loop().run_in_executor(
                    None, llm_response, text, nerfreal)

                logger.info(
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

        logger.info(
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
        params = await request.json()

        sessionid = params.get('sessionid', 0)
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
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filename = fileobj.filename
        filebytes = fileobj.file.read()
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


async def on_shutdown(app):
    # 关闭对等连接
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.info(f'Error: {e}')


async def run(push_url, sessionid):
    nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)
    nerfreals[sessionid] = nerfreal

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    player = HumanPlayer(nerfreals[sessionid])
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type='answer'))
##########################################
# os.environ['MKL_SERVICE_FORCE_INTEL'] = '1'
# os.environ['MULTIPROCESSING_METHOD'] = 'forkserver'
if __name__ == '__main__':
    mp.set_start_method('spawn')
    parser = argparse.ArgumentParser()

    # audio FPS
    parser.add_argument('--fps', type=int, default=50,
                        help="audio fps,must be 50")
    # sliding window left-middle-right length (unit: 20ms)
    parser.add_argument('-l', type=int, default=10)
    parser.add_argument('-m', type=int, default=8)
    parser.add_argument('-r', type=int, default=10)

    parser.add_argument('--W', type=int, default=450, help="GUI width")
    parser.add_argument('--H', type=int, default=450, help="GUI height")

    # musetalk opt
    parser.add_argument('--avatar_id', type=str, default='wav2lip256_avatar1',
                        help="define which avatar in data/avatars")
    # parser.add_argument('--bbox_shift', type=int, default=5)
    parser.add_argument('--batch_size', type=int,
                        default=16, help="infer batch")

    parser.add_argument('--customvideo_config', type=str,
                        default='', help="custom action json")

    # xtts gpt-sovits cosyvoice fishtts tencent doubao indextts2 azuretts
    parser.add_argument('--tts', type=str, default='doubao',
                        help="tts service type")
    parser.add_argument('--REF_FILE', type=str, default="zh_female_xiaohe_uranus_bigtts",
                        help="参考文件名或语音模型ID，默认值为 doubao的语音模型ID zh_female_xiaohe_uranus_bigtts, 若--tts指定为azuretts, 可以使用Azure语音模型ID, 如zh-CN-XiaoxiaoMultilingualNeural")
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

    opt = parser.parse_args()
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
        model = load_model("./models/wav2lip256.pth")
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model, 256)
    elif opt.model == 'ultralight':
        from lightreal import LightReal, load_avatar, load_model, warm_up
        logger.info(opt)
        model = load_model(opt)
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, avatar, 160)
    if opt.transport == 'virtualcam':
        thread_quit = Event()
        nerfreals[0] = build_nerfreal(0)
        rendthrd = Thread(target=nerfreals[0].render, args=(thread_quit,))
        rendthrd.start()

    #############################################################################
    appasync = web.Application(client_max_size=1024**2*100)
    appasync.on_shutdown.append(on_shutdown)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/humanaudio", humanaudio)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/record", record)
    appasync.router.add_post("/interrupt_talk", interrupt_talk)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_static('/', path='web')

    # 配置默认CORS设置
    cors = aiohttp_cors.setup(appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    # 在所有路由上配置CORS
    for route in list(appasync.router.routes()):
        cors.add(route)

    pagename = 'webrtcapi.html'
    if opt.transport == 'rtmp':
        pagename = 'echoapi.html'
    elif opt.transport == 'rtcpush':
        pagename = 'rtcpushapi.html'
    logger.info('start http server; http://<serverip>:' +
                str(opt.listenport)+'/'+pagename)
    logger.info('如果使用webrtc，推荐访问webrtc集成前端: http://<serverip>:' +
                str(opt.listenport)+'/dashboard.html')

    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
        loop.run_until_complete(site.start())
        if opt.transport == 'rtcpush':
            for k in range(opt.max_session):
                push_url = opt.push_url
                if k != 0:
                    push_url = opt.push_url+str(k)
                loop.run_until_complete(run(push_url, k))
        loop.run_forever()
    # Thread(target=run_server, args=(web.AppRunner(appasync),)).start()
    run_server(web.AppRunner(appasync))

    # app.on_shutdown.append(on_shutdown)
    # app.router.add_post("/offer", offer)

    # print('start websocket server')
    # server = pywsgi.WSGIServer(('0.0.0.0', 8000), app, handler_class=WebSocketHandler)
    # server.serve_forever()
