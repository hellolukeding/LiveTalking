
from __future__ import annotations

import asyncio
import base64
import copy
import gzip
import hashlib
import hmac
import json
import logging
import os
import queue
import ssl
import wave
import threading
import time
import uuid
from enum import Enum
from io import BytesIO
from queue import Queue
from threading import Event, Thread
from typing import TYPE_CHECKING, Iterator, Optional

import azure.cognitiveservices.speech as speechsdk
import edge_tts
import numpy as np
import requests
import resampy
import soundfile as sf
import websocket  # pip install websocket-client
import websockets
from av import AudioFrame
from websockets.sync.client import connect  # 也可以选择这种库，但下面示例用 websocket-client

# 假设 BaseTTS 和 logger 已经定义
# from somewhere import BaseTTS, logger, AudioFrame, State


if TYPE_CHECKING:
    from basereal import BaseReal

from logger import logger


class State(Enum):
    RUNNING = 0
    PAUSE = 1


class BaseTTS:
    def __init__(self, opt, parent: BaseReal):
        self.opt = opt
        self.parent = parent

        self.fps = opt.fps  # 20 ms per frame
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // self.fps
        self.input_stream = BytesIO()

        self.msgqueue = Queue()
        self.state = State.RUNNING

        # 🆕 新增：音频轨道支持
        self.audio_track = None
        self.loop = None

    def flush_talk(self):
        self.msgqueue.queue.clear()
        self.state = State.PAUSE

    def put_msg_txt(self, msg: str, datainfo: dict = {}):
        if len(msg) > 0:
            self.msgqueue.put((msg, datainfo))

    def render(self, quit_event, audio_track=None, loop=None):
        # 保存音频轨道引用（供parent使用）
        self.audio_track = audio_track
        self.loop = loop

        # 🆕 如果优化器已存在，设置音频轨道引用
        if hasattr(self, 'optimizer') and self.optimizer is not None:
            try:
                # 更新优化器的音频轨道引用
                if hasattr(self.optimizer, 'audio_track_ready'):
                    self.optimizer.setup_direct_forwarding()
                logger.info("[DOUBAO_TTS] 优化器已配置音频轨道")
            except Exception as e:
                logger.warning(f"[DOUBAO_TTS] 优化器配置失败: {e}")

        process_thread = Thread(target=self.process_tts, args=(quit_event,))
        process_thread.start()

    def process_tts(self, quit_event):
        while not quit_event.is_set():
            try:
                msg: tuple[str, dict] = self.msgqueue.get(
                    block=True, timeout=1)
                self.state = State.RUNNING
                logger.debug(f"[TTS] Received message: {msg[0]}")
            except queue.Empty:
                continue
            try:
                self.txt_to_audio(msg)
                logger.debug(f"[TTS] Completed processing: {msg[0][:50]}...")
            except Exception as e:
                logger.error(f"[TTS] Error processing message: {e}")
        logger.debug('ttsreal thread stop')

    def txt_to_audio(self, msg: tuple[str, dict]):
        pass


###########################################################################################
class EdgeTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        voicename = self.opt.REF_FILE  # "zh-CN-YunxiaNeural"
        text, textevent = msg
        t = time.time()
        asyncio.new_event_loop().run_until_complete(self.__main(voicename, text))
        logger.debug(f'-------edge tts time:{time.time()-t:.4f}s')
        if self.input_stream.getbuffer().nbytes <= 0:  # edgetts err
            logger.error('edgetts err!!!!!')
            return

        self.input_stream.seek(0)
        stream = self.__create_bytes_stream(self.input_stream)

        streamlen = stream.shape[0]
        idx = 0
        while streamlen >= self.chunk and self.state == State.RUNNING:
            eventpoint = {}
            streamlen -= self.chunk
            if idx == 0:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
            elif streamlen < self.chunk:
                eventpoint = {'status': 'end', 'text': text}
                eventpoint.update(**textevent)
            self.parent.put_audio_frame(stream[idx:idx+self.chunk], eventpoint)
            idx += self.chunk

        # 尾帧补齐：避免最后不足一个chunk的尾音被截断
        remain = stream[idx:]
        if remain.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:remain.size] = remain
            eventpoint = {'status': 'end', 'text': text}
            eventpoint.update(**textevent)
            self.parent.put_audio_frame(padded, eventpoint)

        self.input_stream.seek(0)
        self.input_stream.truncate()

    def __create_bytes_stream(self, byte_stream):
        # byte_stream=BytesIO(buffer)
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.debug(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.debug(
                f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.debug(
                f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    async def __main(self, voicename: str, text: str):
        try:
            communicate = edge_tts.Communicate(text, voicename)

            # with open(OUTPUT_FILE, "wb") as file:
            first = True
            async for chunk in communicate.stream():
                if first:
                    first = False
                if chunk["type"] == "audio" and self.state == State.RUNNING:
                    # self.push_audio(chunk["data"])
                    self.input_stream.write(chunk["data"])
                    # file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    pass
        except Exception as e:
            logger.exception('edgetts')

###########################################################################################


class FishTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.fish_speech(
                text,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                "zh",  # en args.language,
                self.opt.TTS_SERVER,  # "http://127.0.0.1:5000", #args.server_url,
            ),
            msg
        )

    def fish_speech(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            'text': text,
            'reference_id': reffile,
            'format': 'wav',
            'streaming': True,
            'use_memory_cache': 'on'
        }
        try:
            res = requests.post(
                f"{server_url}/v1/tts",
                json=req,
                stream=True,
                headers={
                    "content-type": "application/json",
                },
            )
            end = time.perf_counter()
            logger.debug(f"fish_speech Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=17640):  # 1764 44100*20ms*2
                # print('chunk len:',len(chunk))
                if first:
                    end = time.perf_counter()
                    logger.debug(
                        f"fish_speech Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
            # print("gpt_sovits response.elapsed:", res.elapsed)
        except Exception as e:
            logger.exception('fishtts')

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=44100, sr_new=self.sample_rate)
                stream = np.concatenate((last_stream, stream))
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {'status': 'start', 'text': text}
                        # eventpoint={'status':'start','text':text,'msgevent':textevent}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]  # 保留不足一个chunk的尾巴
        if last_stream.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:last_stream.size] = last_stream
            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False
            self.parent.put_audio_frame(padded, eventpoint)
        eventpoint = {'status': 'end', 'text': text}
        # eventpoint={'status':'end','text':text,'msgevent':textevent}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

###########################################################################################


class SovitsTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.gpt_sovits(
                text=text,
                reffile=self.opt.REF_FILE,
                reftext=self.opt.REF_TEXT,
                language="zh",  # en args.language,
                server_url=self.opt.TTS_SERVER,  # "http://127.0.0.1:5000", #args.server_url,
            ),
            msg
        )

    def gpt_sovits(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            'text': text,
            'text_lang': language,
            'ref_audio_path': reffile,
            'prompt_text': reftext,
            'prompt_lang': language,
            'media_type': 'ogg',
            'streaming_mode': True
        }
        # req["text"] = text
        # req["text_language"] = language
        # req["character"] = character
        # req["emotion"] = emotion
        # #req["stream_chunk_size"] = stream_chunk_size  # you can reduce it to get faster response, but degrade quality
        # req["streaming_mode"] = True
        try:
            res = requests.post(
                f"{server_url}/tts",
                json=req,
                stream=True,
            )
            end = time.perf_counter()
            logger.debug(f"gpt_sovits Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return

            first = True

            # 12800 1280 32K*20ms*2
            for chunk in res.iter_content(chunk_size=None):
                logger.debug('chunk len:%d', len(chunk))
                if first:
                    end = time.perf_counter()
                    logger.debug(
                        f"gpt_sovits Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
            # print("gpt_sovits response.elapsed:", res.elapsed)
        except Exception as e:
            logger.exception('sovits')

    def __create_bytes_stream(self, byte_stream):
        # byte_stream=BytesIO(buffer)
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.debug(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.debug(
                f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.debug(
                f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                # stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                # stream = resampy.resample(x=stream, sr_orig=32000, sr_new=self.sample_rate)
                byte_stream = BytesIO(chunk)
                stream = self.__create_bytes_stream(byte_stream)
                stream = np.concatenate((last_stream, stream))
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {'status': 'start', 'text': text}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]  # 保留不足一个chunk的尾巴
        if last_stream.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:last_stream.size] = last_stream
            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False
            self.parent.put_audio_frame(padded, eventpoint)
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

###########################################################################################


class CosyVoiceTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.cosy_voice(
                text,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                "zh",  # en args.language,
                self.opt.TTS_SERVER,  # "http://127.0.0.1:5000", #args.server_url,
            ),
            msg
        )

    def cosy_voice(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        payload = {
            'tts_text': text,
            'prompt_text': reftext
        }
        try:
            files = [('prompt_wav', ('prompt_wav', open(
                reffile, 'rb'), 'application/octet-stream'))]
            res = requests.request(
                "GET", f"{server_url}/inference_zero_shot", data=payload, files=files, stream=True)

            end = time.perf_counter()
            logger.debug(f"cosy_voice Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=9600):  # 960 24K*20ms*2
                if first:
                    end = time.perf_counter()
                    logger.debug(
                        f"cosy_voice Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.exception('cosyvoice')

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=24000, sr_new=self.sample_rate)
                stream = np.concatenate((last_stream, stream))
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {'status': 'start', 'text': text}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]  # 保留不足一个chunk的尾巴
        if last_stream.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:last_stream.size] = last_stream
            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False
            self.parent.put_audio_frame(padded, eventpoint)
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)


###########################################################################################
_PROTOCOL = "https://"
_HOST = "tts.cloud.tencent.com"
_PATH = "/stream"
_ACTION = "TextToStreamAudio"


class TencentTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.appid = os.getenv("TENCENT_APPID")
        self.secret_key = os.getenv("TENCENT_SECRET_KEY")
        self.secret_id = os.getenv("TENCENT_SECRET_ID")
        self.voice_type = int(opt.REF_FILE)
        self.codec = "pcm"
        self.sample_rate = 16000
        self.volume = 0
        self.speed = 0

    def __gen_signature(self, params):
        sort_dict = sorted(params.keys())
        sign_str = "POST" + _HOST + _PATH + "?"
        for key in sort_dict:
            sign_str = sign_str + key + "=" + str(params[key]) + '&'
        sign_str = sign_str[:-1]
        hmacstr = hmac.new(self.secret_key.encode('utf-8'),
                           sign_str.encode('utf-8'), hashlib.sha1).digest()
        s = base64.b64encode(hmacstr)
        s = s.decode('utf-8')
        return s

    def __gen_params(self, session_id, text):
        params = dict()
        params['Action'] = _ACTION
        params['AppId'] = int(self.appid)
        params['SecretId'] = self.secret_id
        params['ModelType'] = 1
        params['VoiceType'] = self.voice_type
        params['Codec'] = self.codec
        params['SampleRate'] = self.sample_rate
        params['Speed'] = self.speed
        params['Volume'] = self.volume
        params['SessionId'] = session_id
        params['Text'] = text

        timestamp = int(time.time())
        params['Timestamp'] = timestamp
        params['Expired'] = timestamp + 24 * 60 * 60
        return params

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.tencent_voice(
                text,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                "zh",  # en args.language,
                self.opt.TTS_SERVER,  # "http://127.0.0.1:5000", #args.server_url,
            ),
            msg
        )

    def tencent_voice(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        session_id = str(uuid.uuid1())
        params = self.__gen_params(session_id, text)
        signature = self.__gen_signature(params)
        headers = {
            "Content-Type": "application/json",
            "Authorization": str(signature)
        }
        url = _PROTOCOL + _HOST + _PATH
        try:
            res = requests.post(url, headers=headers,
                                data=json.dumps(params), stream=True)

            end = time.perf_counter()
            logger.debug(f"tencent Time to make POST: {end-start}s")

            first = True

            for chunk in res.iter_content(chunk_size=6400):  # 640 16K*20ms*2
                # logger.info('chunk len:%d',len(chunk))
                if first:
                    try:
                        rsp = json.loads(chunk)
                        # response["Code"] = rsp["Response"]["Error"]["Code"]
                        # response["Message"] = rsp["Response"]["Error"]["Message"]
                        logger.error("tencent tts:%s",
                                     rsp["Response"]["Error"]["Message"])
                        return
                    except:
                        end = time.perf_counter()
                        logger.debug(
                            f"tencent Time to first chunk: {end-start}s")
                        first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.exception('tencent')

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = np.concatenate((last_stream, stream))
                # stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {'status': 'start', 'text': text}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]  # get the remain stream
        if last_stream.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:last_stream.size] = last_stream
            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False
            self.parent.put_audio_frame(padded, eventpoint)
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

###########################################################################################


class DoubaoTTS(BaseTTS):
    """DoubaoTTS - 简化稳定版"""
    _VOICE_PROBE_CACHE: dict[str, bool] = {}
    _VOICE_PROBE_CACHE_LOCK = threading.Lock()

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.appid = os.getenv("DOUBAO_APPID")
        self.access_key = os.getenv("DOUBAO_ACCESS_TOKEN") or os.getenv(
            "DOUBAO_AccessKeyID") or os.getenv("DOUBAO_TOKEN")
        self.voice_id = opt.REF_FILE or os.getenv("DOUBAO_VOICE_ID")
        self.resource_id = os.getenv("DOUBAO_RESOURCE_ID")
        self.cluster = "volcano_tts"

        logger.info(
            f"[DOUBAO_TTS] 初始化: appid={self.appid}, voice_id={self.voice_id}")

        # WebSocket连接池
        # 重要：TTS 音频若不是 16kHz，需要重采样到 16kHz。
        # - 小块频繁 resample / 频繁 np.concatenate 都会导致卡顿（CPU+内存拷贝）。
        # - 这里保留可配置的 API 采样率，并对重采样做块级聚合，尽量降低开销。
        try:
            requested_sample_rate = int(os.getenv("DOUBAO_TTS_API_SAMPLE_RATE", "24000"))
        except Exception:
            requested_sample_rate = 24000
        if requested_sample_rate not in (8000, 16000, 24000, 48000):
            requested_sample_rate = 24000

        self.api_sample_rate = requested_sample_rate  # 记录API采样率（若服务端不支持会导致重采样兜底）
        self._fallback_voice_candidates = self._build_fallback_voice_candidates()
        self._resolve_working_voice(prefer_different=False, force_refresh=False)
        self.connection_pool = self._create_connection_pool()
        self.optimizer = None
        self._processing_lock = threading.RLock()
        self._edge_fallback_voice = os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
        self._edge_fallback_enabled = os.getenv("DOUBAO_TTS_EDGE_FALLBACK", "false").lower() in ("1", "true", "yes", "on")
        logger.info("[DOUBAO_TTS] 初始化完成")
        self.debug_wav = None
        if os.getenv("DOUBAO_TTS_DEBUG_WAV", "0") == "1":
            try:
                path = os.getenv("DOUBAO_TTS_DEBUG_WAV_PATH") or f"/tmp/debug_doubao_tts_{getattr(opt, 'sessionid', 'session')}.wav"
                self.debug_wav = wave.open(path, "wb")
                self.debug_wav.setnchannels(1)
                self.debug_wav.setsampwidth(2)
                self.debug_wav.setframerate(self.sample_rate)
                logger.info(f"[DOUBAO_TTS] Debug WAV enabled: {path}")
            except Exception as e:
                logger.warning(f"[DOUBAO_TTS] Failed to open debug wav: {e}")
                self.debug_wav = None

    def _auto_integrate_optimizer(self):
        pass

    def _create_connection_pool(self):
        return DoubaoConnectionPool(
            appid=self.appid,
            token=self.access_key,
            voice_id=self.voice_id,
            resource_id=self.resource_id,
            sample_rate=self.api_sample_rate,
            max_connections=10
        )

    def _rebuild_connection_pool(self):
        try:
            if hasattr(self, "connection_pool") and self.connection_pool:
                self.connection_pool.shutdown()
        except Exception:
            pass
        self.connection_pool = self._create_connection_pool()
        logger.info(
            f"[DOUBAO_TTS] Connection pool rebuilt: voice_id={self.voice_id}, resource_id={self.resource_id}"
        )

    def _build_fallback_voice_candidates(self) -> list[str]:
        candidates: list[str] = []
        configured = os.getenv("DOUBAO_FALLBACK_VOICE_IDS", "")
        env_primary = (os.getenv("DOUBAO_VOICE_ID") or "").strip()
        default_primary = "zh_female_tianxinxiaomei_emo_v2_mars_bigtts"
        default_secondary = "zh_male_yangguangqingnian_mars_bigtts"
        for item in [env_primary, default_primary, default_secondary, configured]:
            if not item:
                continue
            if "," in item:
                parts = [part.strip() for part in item.split(",") if part.strip()]
            else:
                parts = [item.strip()]
            for part in parts:
                if part and part not in candidates:
                    candidates.append(part)
        return candidates

    def _resource_candidates(self) -> list[str]:
        candidates: list[str] = []
        configured = (self.resource_id or "").strip()
        if configured:
            candidates.append(configured)
        env_candidates = (os.getenv("DOUBAO_RESOURCE_ID_CANDIDATES") or "").strip()
        if env_candidates:
            for item in env_candidates.split(","):
                item = item.strip()
                if item and item not in candidates:
                    candidates.append(item)
        for default_resource in ("volc.service_type.10029", "seed-tts-1.0"):
            if default_resource not in candidates:
                candidates.append(default_resource)
        return candidates

    def _voice_probe_cache_get(self, key: str) -> Optional[bool]:
        with DoubaoTTS._VOICE_PROBE_CACHE_LOCK:
            return DoubaoTTS._VOICE_PROBE_CACHE.get(key)

    def _voice_probe_cache_set(self, key: str, value: bool):
        with DoubaoTTS._VOICE_PROBE_CACHE_LOCK:
            DoubaoTTS._VOICE_PROBE_CACHE[key] = value

    def _probe_voice_with_resource(self, voice_id: str, resource_id: str) -> bool:
        if not self.appid or not self.access_key:
            return False
        conn = DoubaoWebSocketConnection(
            self.appid,
            self.access_key,
            voice_id,
            resource_id=resource_id,
            sample_rate=self.api_sample_rate
        )
        try:
            if not conn.connect():
                return False
            reqid = str(uuid.uuid4())
            if not conn.send_text_request("你好", reqid, context_texts=[]):
                return False

            deadline = time.time() + 4.0
            while time.time() < deadline:
                chunk = conn.receive_audio_chunk(timeout=1.0)
                if chunk is None:
                    break
                if isinstance(chunk, bytes) and len(chunk) > 0:
                    return True
            return False
        except Exception:
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _resolve_working_voice(self, prefer_different: bool = False, force_refresh: bool = False) -> bool:
        current_voice = (self.voice_id or "").strip()
        candidates = [current_voice] + [v for v in self._fallback_voice_candidates if v and v != current_voice]
        if prefer_different:
            candidates = [v for v in candidates if v != current_voice] + ([current_voice] if current_voice else [])
        candidates = [v for v in candidates if v]
        if not candidates:
            return False

        original_voice = self.voice_id
        original_resource = self.resource_id
        resource_candidates = self._resource_candidates()

        for voice_id in candidates:
            for resource_id in resource_candidates:
                cache_key = f"{voice_id}|{resource_id}"
                cached = None if force_refresh else self._voice_probe_cache_get(cache_key)
                if cached is False:
                    continue
                if cached is True:
                    self.voice_id = voice_id
                    self.resource_id = resource_id
                    self.opt.REF_FILE = voice_id
                    logger.info(
                        f"[DOUBAO_TTS] Use cached healthy voice-resource: voice_id={voice_id}, resource_id={resource_id}"
                    )
                    return True

                ok = self._probe_voice_with_resource(voice_id, resource_id)
                self._voice_probe_cache_set(cache_key, ok)
                if ok:
                    self.voice_id = voice_id
                    self.resource_id = resource_id
                    self.opt.REF_FILE = voice_id
                    logger.info(
                        f"[DOUBAO_TTS] Voice-resource probe success: voice_id={voice_id}, resource_id={resource_id}"
                    )
                    return True

        self.voice_id = original_voice
        self.resource_id = original_resource
        logger.error(
            f"[DOUBAO_TTS] No working Doubao voice found. keep voice_id={self.voice_id}, resource_id={self.resource_id}"
        )
        return False

    def _run_edge_fallback(self, text: str, textevent: dict):
        if not self._edge_fallback_enabled:
            return
        original_ref = getattr(self.opt, "REF_FILE", None)
        try:
            self.opt.REF_FILE = self._edge_fallback_voice
            logger.warning(
                f"[DOUBAO_TTS] Fallback to EdgeTTS voice={self._edge_fallback_voice}, text={text[:40]}..."
            )
            EdgeTTS(self.opt, self.parent).txt_to_audio((text, textevent))
        except Exception as e:
            logger.error(f"[DOUBAO_TTS] Edge fallback failed: {e}")
        finally:
            try:
                self.opt.REF_FILE = original_ref
            except Exception:
                pass

    def _txt_to_audio_impl(self, msg: tuple[str, dict], retried: bool = False):
        text, textevent = msg

        if not text.strip():
            return

        logger.info(f"[DOUBAO_TTS] 处理: {text[:50]}...")

        with self._processing_lock:
            conn = self.connection_pool.get_connection()
            if not conn:
                logger.error("[DOUBAO_TTS] 无法获取连接")
                if not retried and self._resolve_working_voice(prefer_different=True, force_refresh=True):
                    self._rebuild_connection_pool()
                    self._txt_to_audio_impl(msg, retried=True)
                else:
                    self._run_edge_fallback(text, textevent)
                return

            try:
                reqid = str(uuid.uuid4())
                if not conn.send_text_request(text, reqid, context_texts=[]):
                    logger.error("[DOUBAO_TTS] 发送请求失败")
                    self.connection_pool.return_connection(conn)
                    if not retried and self._resolve_working_voice(prefer_different=True, force_refresh=True):
                        self._rebuild_connection_pool()
                        self._txt_to_audio_impl(msg, retried=True)
                    else:
                        self._run_edge_fallback(text, textevent)
                    return

                # 简化的流式处理
                chunk_size = self.chunk  # 320 = 20ms @ 16kHz
                from collections import deque

                class _FloatBuffer:
                    def __init__(self):
                        self._chunks = deque()
                        self._size = 0

                    def push(self, arr: np.ndarray):
                        if arr is None:
                            return
                        if not isinstance(arr, np.ndarray):
                            arr = np.asarray(arr, dtype=np.float32)
                        if arr.dtype != np.float32:
                            arr = arr.astype(np.float32, copy=False)
                        if arr.size <= 0:
                            return
                        self._chunks.append(arr)
                        self._size += int(arr.size)

                    def __len__(self):
                        return self._size

                    def pop(self, n: int) -> Optional[np.ndarray]:
                        if self._size < n:
                            return None
                        out = np.empty(n, dtype=np.float32)
                        pos = 0
                        while pos < n:
                            a = self._chunks[0]
                            take = min(a.size, n - pos)
                            out[pos:pos + take] = a[:take]
                            if take == a.size:
                                self._chunks.popleft()
                            else:
                                self._chunks[0] = a[take:]
                            pos += take
                        self._size -= n
                        return out

                audio_buffer = _FloatBuffer()      # 16kHz float32
                api_rate_buffer = _FloatBuffer()   # api_sample_rate float32
                leftover_bytes = b''
                first_chunk = True
                total_sent = 0
                start_time = None
                # For resampling, process in blocks to reduce overhead.
                api_sr = int(getattr(self, "api_sample_rate", 24000) or 24000)
                out_sr = int(self.sample_rate or 16000)
                # 默认更小分块，降低“突发入队”带来的周期性卡顿风险。
                try:
                    resample_block_ms = int(os.getenv("DOUBAO_RESAMPLE_BLOCK_MS", "40"))
                except Exception:
                    resample_block_ms = 40
                resample_block_ms = max(20, min(500, resample_block_ms))
                resample_block_n = int(api_sr * (resample_block_ms / 1000.0))
                if resample_block_n <= 0:
                    resample_block_n = int(api_sr * 0.1)

                while self.state == State.RUNNING:
                    result = conn.receive_audio_chunk(timeout=5.0)
                    if result is None:
                        break
                    if isinstance(result, bytes) and len(result) == 0:
                        continue
                    if isinstance(result, bytes) and len(result) > 0:
                        result = leftover_bytes + result
                        aligned_len = (len(result) // 2) * 2
                        leftover_bytes = result[aligned_len:]
                        if aligned_len > 0:
                            new_samples = np.frombuffer(
                                result[:aligned_len], dtype=np.int16
                            ).astype(np.float32) / 32767.0

                            if api_sr != out_sr:
                                api_rate_buffer.push(new_samples)
                                while len(api_rate_buffer) >= resample_block_n:
                                    block = api_rate_buffer.pop(resample_block_n)
                                    if block is None:
                                        break
                                    block_out = resampy.resample(block, sr_orig=api_sr, sr_new=out_sr)
                                    audio_buffer.push(block_out)
                            else:
                                audio_buffer.push(new_samples)

                            if self.debug_wav is not None and api_sr == out_sr:
                                try:
                                    self.debug_wav.writeframes((new_samples * 32767).astype(np.int16).tobytes())
                                except Exception:
                                    pass

                        # 发送完整的chunk
                        while len(audio_buffer) >= chunk_size and self.state == State.RUNNING:
                            chunk = audio_buffer.pop(chunk_size)
                            if chunk is None:
                                break

                            eventpoint = {}
                            if first_chunk:
                                eventpoint = {'status': 'start', 'text': text}
                                eventpoint.update(textevent)
                                first_chunk = False
                                start_time = time.perf_counter()

                            self.parent.put_audio_frame(chunk, eventpoint)
                            total_sent += 1

                self.connection_pool.return_connection(conn)

                # 发送剩余数据
                if api_sr != out_sr:
                    # Flush any remaining api-rate samples.
                    try:
                        remaining = api_rate_buffer.pop(len(api_rate_buffer))
                    except Exception:
                        remaining = None
                    if remaining is not None and remaining.size > 0:
                        audio_buffer.push(resampy.resample(remaining, sr_orig=api_sr, sr_new=out_sr))

                # Flush 所有剩余采样，避免句尾丢失（之前只发送一个chunk会截断尾音）
                while len(audio_buffer) > 0 and self.state == State.RUNNING:
                    take_n = min(chunk_size, len(audio_buffer))
                    chunk = audio_buffer.pop(take_n)
                    if chunk is None:
                        break
                    if chunk.size < chunk_size:
                        padded = np.zeros(chunk_size, dtype=np.float32)
                        padded[:chunk.size] = chunk
                        chunk = padded

                    eventpoint = {}
                    if first_chunk:
                        eventpoint = {'status': 'start', 'text': text}
                        eventpoint.update(textevent)
                        first_chunk = False
                    self.parent.put_audio_frame(chunk, eventpoint)
                    total_sent += 1

                if total_sent > 0:
                    eventpoint = {'status': 'end', 'text': text}
                    eventpoint.update(textevent)
                    self.parent.put_audio_frame(
                        np.zeros(chunk_size, dtype=np.float32), eventpoint)
                else:
                    logger.warning("[DOUBAO_TTS] No audio chunks sent")
                    if not retried and self._resolve_working_voice(prefer_different=True, force_refresh=True):
                        self._rebuild_connection_pool()
                        self._txt_to_audio_impl(msg, retried=True)
                    else:
                        logger.warning("[DOUBAO_TTS] Doubao retry failed, switching to Edge fallback")
                        self._run_edge_fallback(text, textevent)

                logger.info(f"[DOUBAO_TTS] 完成: 发送 {total_sent} 个chunk")

            except Exception as e:
                logger.error(f"[DOUBAO_TTS] 异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if not retried and self._resolve_working_voice(prefer_different=True, force_refresh=True):
                    self._rebuild_connection_pool()
                    self._txt_to_audio_impl(msg, retried=True)
                else:
                    self._run_edge_fallback(text, textevent)

    def txt_to_audio(self, msg: tuple[str, dict]):
        self._txt_to_audio_impl(msg, retried=False)

    def get_stats(self):
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

    def cleanup(self):
        """资源清理（供 BaseReal.stop_all_threads 调用）"""
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            if self.debug_wav is not None:
                self.debug_wav.close()
        except Exception:
            pass


# WebSocket连接管理类
class DoubaoWebSocketConnection:
    """单个WebSocket连接包装器 - 基于火山引擎v3 API

    协议格式参考: https://www.volcengine.com/docs/6561/1719100
    """

    def __init__(self, appid: str, token: str, voice_id: str, resource_id: str = None, sample_rate: int = 24000):
        self.appid = appid
        self.token = token
        self.voice_id = voice_id
        self.resource_id = resource_id  # 新增
        self.sample_rate = sample_rate  # 🆕 可配置采样率
        self.cluster = "volcano_tts"

        self.ws = None
        self.is_connected = False
        self.last_used = time.time()
        self.request_count = 0
        self.error_count = 0
        self.lock = threading.Lock()

    def _get_resource_id(self) -> str:
        """获取资源ID - 优先使用已选择的 resource_id"""
        resource = (self.resource_id or "").strip()
        if resource:
            return resource
        return "volc.service_type.10029"

    def connect(self) -> bool:
        """建立WebSocket连接 - 使用v3 API"""
        if self.is_connected and self.ws:
            return True

        try:
            # v3 API端点
            api_url = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"

            # 获取实际使用的 resource_id
            actual_resource_id = self._get_resource_id()
            logger.info(
                f"[WS_MANAGER] 使用 resource_id: {actual_resource_id}, voice_id: {self.voice_id}")

            # v3 API使用HTTP Headers认证
            header = [
                f"X-Api-App-Key: {self.appid}",
                f"X-Api-Access-Key: {self.token}",
                f"X-Api-Resource-Id: {actual_resource_id}",
                f"X-Api-Connect-Id: {str(uuid.uuid4())}",
            ]

            self.ws = websocket.create_connection(
                api_url,
                timeout=10,
                header=header
            )
            self.is_connected = True
            self.last_used = time.time()
            logger.info(f"[WS_MANAGER] WebSocket v3连接成功建立")
            return True
        except Exception as e:
            logger.error(f"[WS_MANAGER] WebSocket连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.is_connected = False
            self.error_count += 1
            return False

    def send_text_request(self, text: str, reqid: str, context_texts: list[str] = None) -> bool:
        """发送文本转语音请求 - 使用v3 API格式

        Args:
            text: 要转换的文本
            reqid: 请求ID
            context_texts: 情感/动作提示列表，如 ["稍作停顿，轻轻眨眼"]
        """
        if not self.is_connected or not self.ws:
            logger.warning("[WS_MANAGER] 连接未就绪，尝试重连...")
            if not self.connect():
                return False

        try:
            # v3 API请求格式
            request_json = {
                "user": {
                    "uid": str(uuid.uuid4()),
                },
                "req_params": {
                    "speaker": self.voice_id,
                    "audio_params": {
                        "format": "pcm",
                        "sample_rate": self.sample_rate,  # 🆕 使用配置的采样率
                        "enable_timestamp": False,
                    },
                    "text": text,
                },
            }

            # 🆕 添加 context_texts 支持（情感/动作提示）
            if context_texts and len(context_texts) > 0:
                if "additions" not in request_json["req_params"]:
                    request_json["req_params"]["additions"] = {}
                request_json["req_params"]["additions"]["context_texts"] = context_texts
                logger.info(f"[WS_MANAGER] 添加 context_texts: {context_texts}")

            # v3 API二进制协议
            # Header: 1字节(版本+header_size) + 1字节(消息类型+flags) + 1字节(序列化+压缩) + 1字节(保留)
            header = bytearray(b'\x11\x10\x11\x00')

            # Payload: gzip压缩的JSON
            payload_bytes = json.dumps(request_json).encode('utf-8')
            payload_bytes = gzip.compress(payload_bytes)

            # 完整请求: header(4字节) + payload_size(4字节) + payload
            full_request = bytearray(header)
            full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
            full_request.extend(payload_bytes)

            with self.lock:
                self.ws.send_binary(bytes(full_request))
                self.last_used = time.time()
                self.request_count += 1

            logger.debug(f"[WS_MANAGER] v3请求发送成功: text_len={len(text)}")
            return True

        except Exception as e:
            logger.error(f"[WS_MANAGER] 发送请求失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.error_count += 1
            self.is_connected = False
            return False

    def receive_audio_chunk(self, timeout: float = 30.0):
        """接收音频数据块 - 解析v3 API响应

        返回值:
        - bytes: 音频数据
        - b'': 继续接收（元数据或ACK）
        - None: 传输结束或错误
        """
        if not self.is_connected or not self.ws:
            logger.warning("[WS_MANAGER] 连接未就绪，无法接收数据")
            return None

        try:
            self.ws.settimeout(timeout)
            result = self.ws.recv()

            with self.lock:
                self.last_used = time.time()

            if not isinstance(result, bytes) or len(result) < 4:
                logger.warning(f"[WS_MANAGER] 收到无效数据: type={type(result)}")
                return None

            # 解析响应头
            header_size = (result[0] & 0x0f) * 4
            message_type = (result[1] >> 4) & 0x0f
            message_flags = result[1] & 0x0f
            compression = result[2] & 0x0f

            payload = result[header_size:] if len(
                result) > header_size else b''

            # 0xb = audio-only server response
            if message_type == 0xb:
                if message_flags == 0:
                    return b''  # ACK，继续接收
                else:
                    if len(payload) >= 8:
                        seq = int.from_bytes(payload[:4], "big", signed=True)

                        if seq < 0:
                            logger.debug("[WS_MANAGER] 收到音频结束标志 (seq < 0)")
                            return None  # 结束

                        # 🆕 修复：正确解析 payload 结构
                        # payload = seq(4) + request_id_len(4) + request_id(N) + audio_len(4) + audio_data
                        offset = 4  # 跳过 seq

                        if len(payload) < offset + 4:
                            return b''

                        request_id_len = int.from_bytes(
                            payload[offset:offset+4], "big")
                        offset += 4 + request_id_len  # 跳过 request_id_len 和 request_id

                        if len(payload) < offset + 4:
                            return b''

                        audio_len = int.from_bytes(
                            payload[offset:offset+4], "big")
                        offset += 4  # 跳过 audio_len

                        audio_data = payload[offset:offset+audio_len]

                        if len(audio_data) > 0:
                            return audio_data

                    return b''

            # 0x9 = full server response (元数据)
            elif message_type == 0x9:
                try:
                    if compression == 1:
                        payload = gzip.decompress(payload)
                    response_str = payload.decode('utf-8', errors='ignore')
                    # 检查是否是结束标志（空的JSON响应 {}）
                    if response_str.strip() == '{}' or response_str.endswith('{}'):
                        logger.debug("[WS_MANAGER] 收到元数据结束标志")
                        return None
                except Exception as e:
                    logger.warning(f"[WS_MANAGER] 解析元数据失败: {e}")
                return b''  # 继续接收

            # 0xf = error response
            elif message_type == 0xf:
                try:
                    if len(payload) >= 8:
                        error_code = int.from_bytes(payload[:4], "big")
                        msg_payload = payload[8:]
                        try:
                            msg_payload = gzip.decompress(msg_payload)
                        except:
                            pass
                        error_msg = msg_payload.decode('utf-8')
                        logger.error(
                            f"[WS_MANAGER] 错误 (code={error_code}): {error_msg}")
                except Exception as e:
                    logger.error(f"[WS_MANAGER] 解析错误失败: {e}")
                return None

            return b''

        except websocket.WebSocketTimeoutException:
            logger.warning(f"[WS_MANAGER] 超时 ({timeout}s)")
            return None
        except websocket.WebSocketConnectionClosedException as e:
            logger.error(f"[WS_MANAGER] WebSocket连接被远程关闭: {e}")
            with self.lock:
                self.error_count += 1
                self.is_connected = False
            return None
        except ssl.SSLError as e:
            logger.error(f"[WS_MANAGER] SSL错误: {e}")
            with self.lock:
                self.error_count += 1
                self.is_connected = False
            return None
        except Exception as e:
            logger.error(f"[WS_MANAGER] 接收失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            with self.lock:
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
        """检查连接健康状态 - 改进版，检测死连接"""
        # 检查WebSocket对象是否存在
        if self.ws is None:
            return False

        # 检查error_count是否超过阈值
        if self.error_count >= 3:
            return False

        # 检查连接是否仍然打开
        try:
            # 检查WebSocket对象的connected状态
            if hasattr(self.ws, 'connected') and not self.ws.connected:
                self.is_connected = False
                logger.debug(f"[WS_MANAGER] 检测到WebSocket已断开 (connected=False)")
                return False
        except Exception as e:
            self.is_connected = False
            logger.debug(f"[WS_MANAGER] 检查连接状态异常: {e}")
            return False

        return self.is_connected and self.error_count < 3


class DoubaoConnectionPool:
    """WebSocket连接池管理器 - 预热连接版

    火山引擎TTS的WebSocket连接是单次请求的，
    但我们可以预先建立连接等待使用，减少首次响应延迟。
    """

    def __init__(self, appid: str, token: str, voice_id: str, resource_id: str = None, sample_rate: int = 16000, max_connections: int = 10):
        self.appid = appid
        self.token = token
        self.voice_id = voice_id
        self.resource_id = resource_id
        self.sample_rate = sample_rate
        self.max_connections = max_connections

        # 预热连接队列
        self._ready_connections = Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        self._running = True

        # 统计信息
        self.total_requests = 0
        self.total_connections = 0
        self.cache_hits = 0

        # 启动预热线程
        self._warmup_thread = threading.Thread(
            target=self._warmup_worker, daemon=True)
        self._warmup_thread.start()

        logger.info(
            f"[WS_POOL] 连接池初始化: sample_rate={sample_rate}, max_connections={max_connections}")

    def _warmup_worker(self):
        """预热连接的后台线程 - 改进版，添加健康监控"""
        last_check_time = time.time()
        while self._running:
            try:
                current_size = self._ready_connections.qsize()

                # 🆕 每30秒记录一次池健康状态
                if time.time() - last_check_time > 30:
                    hit_rate = self.cache_hits / self.total_requests if self.total_requests > 0 else 0
                    logger.info(
                        f"[WS_POOL] 健康状态: 大小={current_size}/{self.max_connections}, "
                        f"命中率={hit_rate:.1%}, 总请求={self.total_requests}, "
                        f"未命中={self.total_connections - self.cache_hits}")
                    last_check_time = time.time()

                # 检查是否需要预热
                if current_size < self.max_connections:
                    conn = self._create_new_connection()
                    if conn:
                        try:
                            self._ready_connections.put(conn, timeout=1.0)
                            logger.debug(
                                f"[WS_POOL] 预热连接已就绪 (队列: {self._ready_connections.qsize()})")
                        except:
                            conn.close()
                time.sleep(0.5)  # 每0.5秒检查一次
            except Exception as e:
                logger.error(f"[WS_POOL] 预热线程异常: {e}")
                time.sleep(1.0)

    def _create_new_connection(self):
        """创建新连接"""
        conn = DoubaoWebSocketConnection(
            self.appid, self.token, self.voice_id,
            self.resource_id, self.sample_rate
        )

        if conn.connect():
            with self._lock:
                self.total_connections += 1
            return conn
        return None

    def get_connection(self, timeout: float = 10.0):
        """获取连接 - 优先从预热队列获取，支持重连"""
        with self._lock:
            self.total_requests += 1

        # 1. 尝试从预热队列获取
        try:
            conn = self._ready_connections.get(timeout=0.1)
            if conn and conn.is_healthy():
                with self._lock:
                    self.cache_hits += 1
                logger.debug(
                    f"[WS_POOL] 使用预热连接 (命中率: {self.cache_hits}/{self.total_requests})")
                return conn
            elif conn:
                conn.close()
        except:
            pass

        # 2. 预热队列为空，创建新连接
        logger.debug(f"[WS_POOL] 预热队列为空，创建新连接...")
        new_conn = self._create_new_connection()

        # 3. 如果创建失败，尝试重连机制
        if not new_conn:
            logger.warning("[WS_POOL] 首次连接失败，启动重连机制...")
            for retry in range(3):
                logger.info(f"[WS_POOL] 重连尝试 {retry + 1}/3...")
                time.sleep(1.0)  # 等待1秒后重试
                new_conn = self._create_new_connection()
                if new_conn:
                    logger.info(f"[WS_POOL] 重连成功!")
                    break
            else:
                logger.error("[WS_POOL] 重连失败，无法建立连接")
                return None

        return new_conn

    def return_connection(self, conn):
        """归还连接 - 健康连接复用，不健康连接才关闭并重新创建"""
        if not conn:
            return
        
        # 检查连接是否健康
        if conn.is_healthy():
            try:
                # 尝试归还到预热队列，增加等待时间
                self._ready_connections.put(conn, timeout=1.0)
                logger.debug(f"[WS_POOL] 连接已归还到池中 (当前池大小: {self._ready_connections.qsize()})")
                return
            except queue.Full:
                # 队列确实满了，关闭最老的非活跃连接
                logger.warning("[WS_POOL] 连接池已满，关闭当前连接")
                conn.close()
            except Exception as e:
                logger.debug(f"[WS_POOL] 归还连接异常: {e}")
        else:
            logger.warning(f"[WS_POOL] 连接不健康 (error_count={conn.error_count})，关闭并重新创建")
            conn.close()
            # 🆕 改进：确保新连接成功创建并加入池子，增加重试逻辑
            max_retries = 3
            for retry in range(max_retries):
                new_conn = self._create_new_connection()
                if new_conn:
                    try:
                        self._ready_connections.put(new_conn, timeout=2.0)  # 增加超时到2秒
                        logger.info(f"[WS_POOL] 不健康连接已替换 (池大小: {self._ready_connections.qsize()})")
                        break
                    except queue.Full:
                        logger.debug(f"[WS_POOL] 连接池已满，关闭新连接")
                        new_conn.close()
                        break
                    except Exception as e:
                        logger.debug(f"[WS_POOL] 归还新连接异常: {e}")
                logger.warning(f"[WS_POOL] 重试创建连接 {retry+1}/{max_retries}")
                if retry < max_retries - 1:
                    time.sleep(0.1)  # 短暂等待后重试

    def get_stats(self):
        """获取统计"""
        return {
            "total_connections": self.total_connections,
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "ready_connections": self._ready_connections.qsize(),
        }

    def shutdown(self):
        """关闭连接池"""
        self._running = False
        # 清空预热队列
        while not self._ready_connections.empty():
            try:
                conn = self._ready_connections.get_nowait()
                conn.close()
            except:
                pass
        logger.info("[WS_POOL] 连接池已关闭")

###########################################################################################


class IndexTTS2(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        # IndexTTS2 配置参数
        self.server_url = opt.TTS_SERVER  # Gradio服务器地址，如 "http://127.0.0.1:7860/"
        self.ref_audio_path = opt.REF_FILE  # 参考音频文件路径
        self.max_tokens = getattr(opt, 'MAX_TOKENS', 120)  # 最大token数

        # 初始化Gradio客户端
        try:
            from gradio_client import Client, handle_file
            self.client = Client(self.server_url)
            self.handle_file = handle_file
            logger.debug(f"IndexTTS2 Gradio客户端初始化成功: {self.server_url}")
        except ImportError:
            logger.error(
                "IndexTTS2 需要安装 gradio_client: pip install gradio_client")
            raise
        except Exception as e:
            logger.error(f"IndexTTS2 Gradio客户端初始化失败: {e}")
            raise

    def txt_to_audio(self, msg):
        text, textevent = msg
        try:
            # 先进行文本分割
            segments = self.split_text(text)
            if not segments:
                logger.error("IndexTTS2 文本分割失败")
                return

            logger.debug(f"IndexTTS2 文本分割为 {len(segments)} 个片段")

            # 循环生成每个片段的音频
            for i, segment_text in enumerate(segments):
                if self.state != State.RUNNING:
                    break

                logger.debug(f"IndexTTS2 正在生成第 {i+1}/{len(segments)} 段音频...")
                audio_file = self.indextts2_generate(segment_text)

                if audio_file:
                    # 为每个片段创建事件信息
                    segment_msg = (segment_text, textevent)
                    self.file_to_stream(audio_file, segment_msg, is_first=(
                        i == 0), is_last=(i == len(segments)-1))
                else:
                    logger.error(f"IndexTTS2 第 {i+1} 段音频生成失败")

        except Exception as e:
            logger.exception(f"IndexTTS2 txt_to_audio 错误: {e}")

    def split_text(self, text):
        """使用 IndexTTS2 API 分割文本"""
        try:
            logger.debug(f"IndexTTS2 开始分割文本，长度: {len(text)}")

            # 调用文本分割 API
            result = self.client.predict(
                text=text,
                max_text_tokens_per_segment=self.max_tokens,
                api_name="/on_input_text_change"
            )

            # 解析分割结果
            if 'value' in result and 'data' in result['value']:
                data = result['value']['data']
                logger.debug(f"IndexTTS2 共分割为 {len(data)} 个片段")

                segments = []
                for i, item in enumerate(data):
                    序号 = item[0] + 1
                    分句内容 = item[1]
                    token数 = item[2]
                    logger.debug(f"片段 {序号}: {len(分句内容)} 字符, {token数} tokens")
                    segments.append(分句内容)

                return segments
            else:
                logger.error(f"IndexTTS2 文本分割结果格式异常: {result}")
                return [text]  # 如果分割失败，返回原文本

        except Exception as e:
            logger.exception(f"IndexTTS2 文本分割失败: {e}")
            return [text]  # 如果分割失败，返回原文本

    def indextts2_generate(self, text):
        """调用 IndexTTS2 Gradio API 生成语音"""
        start = time.perf_counter()

        try:
            # 调用 gen_single API
            result = self.client.predict(
                emo_control_method="Same as the voice reference",
                prompt=self.handle_file(self.ref_audio_path),
                text=text,
                emo_ref_path=self.handle_file(self.ref_audio_path),
                emo_weight=0.8,
                vec1=0.5,
                vec2=0,
                vec3=0,
                vec4=0,
                vec5=0,
                vec6=0,
                vec7=0,
                vec8=0,
                emo_text="",
                emo_random=False,
                max_text_tokens_per_segment=self.max_tokens,
                param_16=True,
                param_17=0.8,
                param_18=30,
                param_19=0.8,
                param_20=0,
                param_21=3,
                param_22=10,
                param_23=1500,
                api_name="/gen_single"
            )

            end = time.perf_counter()
            logger.debug(f"IndexTTS2 片段生成完成，耗时: {end-start:.2f}s")

            # 返回生成的音频文件路径
            if 'value' in result:
                audio_file = result['value']
                return audio_file
            else:
                logger.error(f"IndexTTS2 结果格式异常: {result}")
                return None

        except Exception as e:
            logger.exception(f"IndexTTS2 API调用失败: {e}")
            return None

    def file_to_stream(self, audio_file, msg, is_first=False, is_last=False):
        """将音频文件转换为音频流"""
        text, textevent = msg

        try:
            # 读取音频文件
            stream, sample_rate = sf.read(audio_file)
            logger.debug(f'IndexTTS2 音频文件 {sample_rate}Hz: {stream.shape}')

            # 转换为float32
            stream = stream.astype(np.float32)

            # 如果是多声道，只取第一个声道
            if stream.ndim > 1:
                logger.debug(f'IndexTTS2 音频有 {stream.shape[1]} 个声道，只使用第一个')
                stream = stream[:, 0]

            # 重采样到目标采样率
            if sample_rate != self.sample_rate and stream.shape[0] > 0:
                logger.debug(
                    f'IndexTTS2 重采样: {sample_rate}Hz -> {self.sample_rate}Hz')
                stream = resampy.resample(
                    x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

            # 分块发送音频流
            streamlen = stream.shape[0]
            idx = 0
            first_chunk = True

            while streamlen >= self.chunk and self.state == State.RUNNING:
                eventpoint = None

                # 只在第一个片段的第一个chunk发送start事件
                if is_first and first_chunk:
                    eventpoint = {'status': 'start',
                                  'text': text, 'msgevent': textevent}
                    first_chunk = False

                self.parent.put_audio_frame(
                    stream[idx:idx + self.chunk], eventpoint)
                idx += self.chunk
                streamlen -= self.chunk

            # 补发最后不足一个chunk的尾音，避免片段末尾被截断
            remain = stream[idx:]
            if remain.size > 0 and self.state == State.RUNNING:
                padded = np.zeros(self.chunk, dtype=np.float32)
                padded[:remain.size] = remain
                eventpoint = None
                if is_first and first_chunk:
                    eventpoint = {'status': 'start',
                                  'text': text, 'msgevent': textevent}
                    first_chunk = False
                self.parent.put_audio_frame(padded, eventpoint)

            # 只在最后一个片段发送end事件
            if is_last:
                eventpoint = {'status': 'end',
                              'text': text, 'msgevent': textevent}
                self.parent.put_audio_frame(
                    np.zeros(self.chunk, np.float32), eventpoint)

            # 清理临时文件
            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
                    logger.debug(f"IndexTTS2 已删除临时文件: {audio_file}")
            except Exception as e:
                logger.warning(f"IndexTTS2 删除临时文件失败: {e}")

        except Exception as e:
            logger.exception(f"IndexTTS2 音频流处理失败: {e}")

###########################################################################################


class XTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.speaker = self.get_speaker(opt.REF_FILE, opt.TTS_SERVER)

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.xtts(
                text,
                self.speaker,
                "zh-cn",  # en args.language,
                self.opt.TTS_SERVER,  # "http://localhost:9000", #args.server_url,
                "20"  # args.stream_chunk_size
            ),
            msg
        )

    def get_speaker(self, ref_audio, server_url):
        files = {"wav_file": ("reference.wav", open(ref_audio, "rb"))}
        response = requests.post(f"{server_url}/clone_speaker", files=files)
        return response.json()

    def xtts(self, text, speaker, language, server_url, stream_chunk_size) -> Iterator[bytes]:
        start = time.perf_counter()
        speaker["text"] = text
        speaker["language"] = language
        # you can reduce it to get faster response, but degrade quality
        speaker["stream_chunk_size"] = stream_chunk_size
        try:
            res = requests.post(
                f"{server_url}/tts_stream",
                json=speaker,
                stream=True,
            )
            end = time.perf_counter()
            logger.debug(f"xtts Time to make POST: {end-start}s")

            if res.status_code != 200:
                print("Error:", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=9600):  # 24K*20ms*2
                if first:
                    end = time.perf_counter()
                    logger.debug(f"xtts Time to first chunk: {end-start}s")
                    first = False
                if chunk:
                    yield chunk
        except Exception as e:
            print(e)

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=24000, sr_new=self.sample_rate)
                stream = np.concatenate((last_stream, stream))
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {'status': 'start', 'text': text}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]  # 保留不足一个chunk的尾巴
        if last_stream.size > 0 and self.state == State.RUNNING:
            padded = np.zeros(self.chunk, dtype=np.float32)
            padded[:last_stream.size] = last_stream
            eventpoint = {}
            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False
            self.parent.put_audio_frame(padded, eventpoint)
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

###########################################################################################


class AzureTTS(BaseTTS):
    CHUNK_SIZE = 640  # 16kHz, 20ms, 16-bit Mono PCM size

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.audio_buffer = b''
        voicename = self.opt.REF_FILE   # 比如"zh-CN-XiaoxiaoMultilingualNeural"
        speech_key = os.getenv("AZURE_SPEECH_KEY")
        tts_region = os.getenv("AZURE_TTS_REGION")
        speech_endpoint = f"wss://{tts_region}.tts.speech.microsoft.com/cognitiveservices/websocket/v2"
        speech_config = speechsdk.SpeechConfig(
            subscription=speech_key, endpoint=speech_endpoint)
        speech_config.speech_synthesis_voice_name = voicename
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm)

        # 获取内存中流形式的结果
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None)
        self.speech_synthesizer.synthesizing.connect(self._on_synthesizing)

    def txt_to_audio(self, msg: tuple[str, dict]):
        msg_text: str = msg[0]
        result = self.speech_synthesizer.speak_text(msg_text)

        # 延迟指标
        fb_latency = int(result.properties.get_property(
            speechsdk.PropertyId.SpeechServiceResponse_SynthesisFirstByteLatencyMs
        ))
        fin_latency = int(result.properties.get_property(
            speechsdk.PropertyId.SpeechServiceResponse_SynthesisFinishLatencyMs
        ))
        logger.debug(
            f"azure音频生成相关：首字节延迟: {fb_latency} ms, 完成延迟: {fin_latency} ms, result_id: {result.result_id}")

    # === 回调 ===

    def _on_synthesizing(self, evt: speechsdk.SpeechSynthesisEventArgs):
        if evt.result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.debug("SynthesizingAudioCompleted")
        elif evt.result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = evt.result.cancellation_details
            logger.debug(
                f"Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    logger.debug(
                        f"Error details: {cancellation_details.error_details}")
        if self.state != State.RUNNING:
            self.audio_buffer = b''
            return

        # evt.result.audio_data 是刚到的一小段原始 PCM
        self.audio_buffer += evt.result.audio_data
        while len(self.audio_buffer) >= self.CHUNK_SIZE:
            chunk = self.audio_buffer[:self.CHUNK_SIZE]
            self.audio_buffer = self.audio_buffer[self.CHUNK_SIZE:]

            frame = (np.frombuffer(chunk, dtype=np.int16)
                       .astype(np.float32) / 32767.0)
            self.parent.put_audio_frame(frame)
