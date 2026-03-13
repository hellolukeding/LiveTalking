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

import asyncio
import copy
import glob
import math
# from .utils import *
import os
import pickle
import queue
import re
import time
from queue import Queue
from threading import Event, Thread

import cv2
import numpy as np
import torch
import torch.multiprocessing as mp
from av import AudioFrame, VideoFrame
from basereal import BaseReal
from lipasr import LipASR
from logger import logger
from tencentasr import TencentApiAsr
from tqdm import tqdm

from wav2lip.models.wav2lip_384 import Wav2Lip

# from imgcache import ImgCache


device = "cuda" if torch.cuda.is_available() else ("mps" if (hasattr(
    torch.backends, "mps") and torch.backends.mps.is_available()) else "cpu")
print('Using {} for inference.'.format(device))


def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path, weights_only=True)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage,
                                weights_only=True)
    return checkpoint


def load_model(path):
    model = Wav2Lip()
    logger.debug("Load checkpoint from: {}".format(path))
    checkpoint = _load(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace('module.', '')] = v
    model.load_state_dict(new_s)

    model = model.to(device)
    return model.eval()


def load_avatar(avatar_id):
    """
    加载 avatar 数据，    同时返回帧数据和元数据（包括名字）

    Returns:
        tuple: (frame_list_cycle, face_list_cycle, coord_list_cycle, meta_dict)
    """
    # Validate avatar_id format (only alphanumeric, underscore, hyphen)
    if not re.match(r'^[a-zA-Z0-9_-]+$', avatar_id):
        raise ValueError(f"Invalid avatar_id format: {avatar_id}")

    # Use pathlib for safe path operations
    from pathlib import Path
    avatars_root = Path("./data/avatars").resolve()
    avatar_path = (avatars_root / avatar_id).resolve()

    # Ensure the resolved path is within avatars_root (prevent path traversal)
    if not str(avatar_path).startswith(str(avatars_root)):
        raise ValueError(f"Path traversal attempt detected: {avatar_id}")

    full_imgs_path = avatar_path / "full_imgs"
    face_imgs_path = avatar_path / "face_imgs"
    coords_path = avatar_path / "coords.pkl"
    meta_path = avatar_path / "meta.json"

    # 读取 meta.json 获取 avatar 名字
    meta = {}
    if meta_path.exists():
        import json
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    avatar_name = meta.get('name', avatar_id)  # 默认使用 avatar_id

    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)
    input_img_list = glob.glob(os.path.join(
        str(full_imgs_path), '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(input_img_list, key=lambda x: int(
        os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)
    # self.imagecache = ImgCache(len(self.coord_list_cycle),self.full_imgs_path,1000)
    input_face_list = glob.glob(os.path.join(
        str(face_imgs_path), '*.[jpJP][pnPN]*[gG]'))
    input_face_list = sorted(input_face_list, key=lambda x: int(
        os.path.splitext(os.path.basename(x))[0]))
    face_list_cycle = read_imgs(input_face_list)

    return frame_list_cycle, face_list_cycle, coord_list_cycle, avatar_name


@torch.no_grad()
def warm_up(batch_size, model, modelres):
    # 预热函数
    logger.debug('warmup model...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)


def read_imgs(img_list):
    frames = []
    logger.debug('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames


def __mirror_index(size, index):
    # size = len(self.coord_list_cycle)
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1


def inference(quit_event, batch_size, face_list_cycle, audio_feat_queue, audio_out_queue, res_frame_queue, model, owner=None):

    # model = load_model("./models/wav2lip.pth")
    # input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    # input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    # face_list_cycle = read_imgs(input_face_list)

    # input_latent_list_cycle = torch.load(latents_out_path)
    length = len(face_list_cycle)
    index = 0
    count = 0
    counttime = 0
    logger.debug('start inference')
    while not quit_event.is_set():
        starttime = time.perf_counter()
        mel_batch = []
        try:
            mel_batch = audio_feat_queue.get(block=True, timeout=1)
        except queue.Empty:
            continue

        is_all_silence = True
        audio_frames = []
        for _ in range(batch_size*2):
            frame, type, eventpoint = audio_out_queue.get()
            audio_frames.append((frame, type, eventpoint))
            if type == 0:
                is_all_silence = False  # 修复拼写错误

        if is_all_silence:
            for i in range(batch_size):
                res_frame_queue.put((None, __mirror_index(length, index),
                        audio_frames[i*2:i*2+2]))
                index = index + 1
        else:
            # print('infer=======')
            t = time.perf_counter()
            img_batch = []
            for i in range(batch_size):
                idx = __mirror_index(length, index+i)
                face = face_list_cycle[idx]
                img_batch.append(face)
            img_batch, mel_batch = np.asarray(img_batch), np.asarray(mel_batch)

            # 验证 face 形状是否有效
            if face.size == 0 or len(face.shape) < 2:
                raise ValueError(f"Invalid face shape: {face.shape}")

            img_masked = img_batch.copy()
            img_masked[:, face.shape[0]//2:] = 0

            img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.
            mel_batch = np.reshape(
                mel_batch, [len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1])

            img_batch = torch.FloatTensor(
                np.transpose(img_batch, (0, 3, 1, 2))).to(device)
            mel_batch = torch.FloatTensor(
                np.transpose(mel_batch, (0, 3, 1, 2))).to(device)

            with torch.no_grad():
                pred = model(mel_batch, img_batch)
            pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.

            counttime += (time.perf_counter() - t)
            count += batch_size
            # _totalframe += 1
            if count >= 100:
                logger.debug(
                    f"------actual avg infer fps:{count/counttime:.4f}")
                count = 0
                counttime = 0
            for i, res_frame in enumerate(pred):
                res_frame_queue.put((res_frame, __mirror_index(
                    length, index), audio_frames[i*2:i*2+2]))
                index = index + 1
            # print('total batch time:',time.perf_counter()-starttime)
    logger.debug('lipreal inference processor stop')


class LipReal(BaseReal):
    @torch.no_grad()
    def __init__(self, opt, model, avatar, avatar_name=None):
        super().__init__(opt)
        # self.opt = opt # shared with the trainer's opt to support in-place modification of rendering parameters.
        # self.W = opt.W
        # self.H = opt.H

        self.fps = opt.fps  # 20 ms per frame

        self.batch_size = opt.batch_size
        self.idx = 0
        self.res_frame_queue = Queue(self.batch_size*2)  # mp.Queue
        # 周期性指标上报线程（每10s输出一次可观测指标）
        self._metrics_running = True
        self._metrics_thread = Thread(target=self._metrics_logger, daemon=True)
        self._metrics_thread.start()
        # self.__loadavatar()
        self.model = model
        self.frame_list_cycle, self.face_list_cycle, self.coord_list_cycle = avatar
        # 存储 avatar 名字， 用于系统提示词
        self.avatar_name = avatar_name or "小li"

        # 🚀 延迟初始化 ASR 以加快 /offer 响应速度
        # ASR 初始化可能涉及凭据验证等耗时操作，放在 render() 中异步执行
        self.lip_asr = None
        self.tencent_asr = None
        self._asr_initialized = False

        # ASR音频收集缓冲区
        self.asr_audio_buffer = []
        self.asr_buffer_lock = mp.Lock()

        # 防止并发调用腾讯 ASR（避免多个重叠请求导致排队延迟）
        self._asr_running = False

        self.render_event = mp.Event()

    def _ensure_asr_initialized(self):
        """延迟初始化 ASR（线程安全）"""
        if self._asr_initialized:
            return
        logger.info(f"[LipReal] 延迟初始化 ASR")
        # 保留LipASR用于口型驱动的特征提取
        self.lip_asr = LipASR(self.opt, self)
        self.lip_asr.warm_up()

        # 新增腾讯ASR用于文本识别
        try:
            self.tencent_asr = TencentApiAsr(self.opt, self)
        except Exception as e:
            logger.warning(f"[LipReal] TencentApiAsr 初始化失败（可选功能）: {e}")
            self.tencent_asr = None

        self._asr_initialized = True
        logger.info(f"[LipReal] ASR 初始化完成")

    # def __del__(self):
    #     logger.info(f'lipreal({self.sessionid}) delete')

    def paste_back_frame(self, pred_frame, idx: int):
        bbox = self.coord_list_cycle[idx]
        combine_frame = copy.deepcopy(self.frame_list_cycle[idx])
        # combine_frame = copy.deepcopy(self.imagecache.get_img(idx))
        y1, y2, x1, x2 = bbox
        res_frame = cv2.resize(pred_frame.astype(np.uint8), (x2-x1, y2-y1))
        # combine_frame = get_image(ori_frame,res_frame,bbox)
        # t=time.perf_counter()
        combine_frame[y1:y2, x1:x2] = res_frame
        return combine_frame

    async def _run_tencent_asr(self, audio_data: bytes):
        """
        运行腾讯ASR进行文本识别
        Args:
            audio_data: 音频数据 (bytes)
        """
        # 如果已有 ASR 任务在运行，则跳过本次触发以减少排队延迟
        if getattr(self, '_asr_running', False):
            logger.debug(
                "[Tencent ASR] Previous ASR task still running, skip this trigger")
            return None

        try:
            self._asr_running = True
            logger.debug("[Tencent ASR] Starting recognition...")

            import numpy as _np
            total_start = time.perf_counter()

            # 转换（如果需要）
            convert_start = time.perf_counter()
            if hasattr(audio_data, 'dtype') or isinstance(audio_data, (list, tuple)):
                loop = asyncio.get_running_loop()
                wav_bytes = await loop.run_in_executor(None, self.tencent_asr._pcm_to_wav_bytes, _np.array(audio_data, dtype=_np.float32), 16000)
            else:
                wav_bytes = audio_data
            convert_ms = (time.perf_counter() - convert_start) * 1000

            # 请求识别
            req_start = time.perf_counter()
            text = await self.tencent_asr.recognize(wav_bytes)
            req_ms = (time.perf_counter() - req_start) * 1000

            total_ms = (time.perf_counter() - total_start) * 1000
            logger.debug(
                f"[Tencent ASR METRICS] convert_ms={convert_ms:.1f} req_ms={req_ms:.1f} total_ms={total_ms:.1f} success={bool(text)}")

            if text:
                self.send_custom_msg(f"ASR_RESULT:{text}")

            return text
        except Exception as e:
            # 记录失败的时序埋点（如果可能）
            try:
                total_ms = (time.perf_counter() - total_start) * 1000
                logger.debug(
                    f"[Tencent ASR METRICS] total_ms={total_ms:.1f} success=False error={e}")
            except Exception:
                pass
            logger.error(f"[Tencent ASR] Error: {e}")
            return None
        finally:
            try:
                self._asr_running = False
            except Exception:
                pass

    def _collect_audio_data(self, duration_ms: int = 2000):
        """
        收集指定时长的音频数据用于腾讯ASR
        Args:
            duration_ms: 收集的音频时长（毫秒）
        Returns:
            numpy.ndarray: 单通道 float32 PCM 数组（采样率 16k），可能为空数组
        """
        # 优先使用 WebRTC 音频缓冲区（内部为 float32 列表）
        with self.asr_buffer_lock:
            if len(self.asr_audio_buffer) > 0:
                samples_needed = int(16000 * duration_ms / 1000)
                audio_data = np.array(
                    self.asr_audio_buffer[:samples_needed], dtype=np.float32)
                self.asr_audio_buffer = self.asr_audio_buffer[samples_needed:]
                return audio_data

        # 如果 ASR 未初始化或缓冲区为空，返回空数组
        if self.lip_asr is None:
            return np.array([], dtype=np.float32)

        # 如果缓冲区为空，从 LipASR 输出队列收集若干帧（每帧约20ms）
        frames_needed = int(duration_ms / 20)
        audio_frames = []

        for _ in range(frames_needed):
            try:
                frame, type, _ = self.lip_asr.output_queue.get(timeout=0.1)
                if type == 0:  # 正常语音帧
                    audio_frames.append(frame)
            except queue.Empty:
                break

        if not audio_frames:
            return np.array([], dtype=np.float32)

        audio_data = np.concatenate(audio_frames)
        return audio_data

    def add_asr_audio(self, audio_frame: np.ndarray):
        """
        添加音频帧到ASR缓冲区
        Args:
            audio_frame: 音频帧 (numpy数组)
        """
        with self.asr_buffer_lock:
            self.asr_audio_buffer.extend(audio_frame.tolist())
            # 限制缓冲区大小为最多10秒的音频
            max_buffer_size = 16000 * 10
            if len(self.asr_audio_buffer) > max_buffer_size:
                self.asr_audio_buffer = self.asr_audio_buffer[-max_buffer_size:]

    def _metrics_logger(self):
        """周期性输出关键运行指标，便于长期观察压力点（每10s）"""
        while getattr(self, '_metrics_running', False):
            try:
                video_drops = getattr(self, '_video_drop_count', 0)
                res_qsize = self.res_frame_queue.qsize() if hasattr(
                    self, 'res_frame_queue') else -1
                logger.info(
                    f"[METRICS] res_drop_count={getattr(self, 'res_drop_count', 0)} video_drop={video_drops} res_qsize={res_qsize}")
            except Exception:
                pass
            time.sleep(10)

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        # 保存音频轨道引用到父类
        self.audio_track = audio_track
        self.loop = loop

        # 🆕 存储 render quit_event 作为实例变量，方便外部清理时访问
        self.__render_quit_event = quit_event

        # 🚀 延迟初始化 ASR 和 TTS（首次 render 时执行）
        self._ensure_asr_initialized()
        self._ensure_tts_initialized()

        # if self.opt.asr:
        #     self.asr.warm_up()

        self.init_customindex()
        # Start delayed audio output worker (for A/V sync) if enabled.
        try:
            self.start_audio_out_worker(quit_event)
        except Exception:
            pass
        # 传递音频轨道给TTS
        if self.tts:
            self.tts.render(quit_event, audio_track, loop)

        # Flush any pending audio frames that were buffered before the audio track or its loop was ready
        try:
            self._flush_pending_audio()
        except Exception:
            logger.debug('Failed to flush pending audio frames on render')

        # 🆕 使用实例变量存储线程和事件，方便外部访问
        infer_quit_event = Event()
        self.__infer_quit_event = infer_quit_event
        infer_thread = Thread(target=inference, args=(infer_quit_event, self.batch_size, self.face_list_cycle,
                                                      self.lip_asr.feat_queue, self.lip_asr.output_queue, self.res_frame_queue,
                                                      self.model, self))  # mp.Process
        self._infer_thread = infer_thread
        infer_thread.start()

        process_quit_event = Event()
        self.__process_quit_event = process_quit_event
        process_thread = Thread(target=self.process_frames, args=(
            process_quit_event, loop, audio_track, video_track))
        self._process_thread = process_thread
        process_thread.start()

        # self.render_event.set() #start infer process render
        count = 0
        totaltime = 0
        _starttime = time.perf_counter()
        # _totalframe=0

        # 腾讯ASR相关变量
        # 腾讯ASR相关变量
        asr_count = 0
        # 支持通过环境变量调整 ASR 触发频率与采样时长，便于在延迟/准确率之间权衡
        try:
            asr_interval = int(os.getenv('ASR_INTERVAL_FRAMES', '25'))
        except Exception:
            asr_interval = 25
        try:
            asr_duration_ms = int(os.getenv('TENCENT_ASR_DURATION_MS', '1000'))
        except Exception:
            asr_duration_ms = 1000

        while not quit_event.is_set():
            # update texture every frame
            # audio stream thread...
            t = time.perf_counter()
            # 运行LipASR用于口型驱动的特征提取
            if self.lip_asr:
                self.lip_asr.run_step()

            # 定期运行腾讯ASR进行文本识别
            asr_count += 1
            if asr_count >= asr_interval and self.tencent_asr:
                asr_count = 0
                # 收集音频数据并运行腾讯ASR
                try:
                    # 收集指定时长的音频作为单次识别单元，避免过长导致异步任务/延迟
                    audio_data = self._collect_audio_data(asr_duration_ms)
                    if len(audio_data) > 1000:  # 确保有足够的音频数据
                        try:
                            # 优先将协程安全地提交到传入的事件循环（如果在运行）
                            if loop is not None and getattr(loop, 'is_running', lambda: False)():
                                try:
                                    asyncio.run_coroutine_threadsafe(
                                        self._run_tencent_asr(audio_data), loop)
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to schedule Tencent ASR on provided loop: {e}; will run in background thread")

                                    def _bg():
                                        try:
                                            asyncio.run(
                                                self._run_tencent_asr(audio_data))
                                        except Exception as e:
                                            logger.warning(
                                                f"Background ASR run failed: {e}")

                                    Thread(target=_bg, daemon=True).start()
                            else:
                                # 没有可用的运行中事件循环，改为在后台线程中运行协程，避免阻塞渲染主循环或抛出 "no running event loop"

                                def _bg_run():
                                    try:
                                        asyncio.run(
                                            self._run_tencent_asr(audio_data))
                                    except Exception as e:
                                        logger.warning(
                                            f"Background ASR run failed: {e}")

                                Thread(target=_bg_run, daemon=True).start()
                        except Exception as e:
                            logger.warning(f"Failed to run Tencent ASR: {e}")
                except Exception as e:
                    logger.warning(f"Failed to run Tencent ASR: {e}")

            # if video_track._queue.qsize()>=2*self.opt.batch_size:
            #     print('sleep qsize=',video_track._queue.qsize())
            #     time.sleep(0.04*video_track._queue.qsize()*0.8)
            if video_track and video_track._queue.qsize() >= 5:
                logger.debug('sleep qsize=%d', video_track._queue.qsize())
                time.sleep(0.04*video_track._queue.qsize()*0.8)

            # delay = _starttime+_totalframe*0.04-time.perf_counter() #40ms
            # if delay > 0:
            #     time.sleep(delay)
        # self.render_event.clear() #end infer process render
        logger.debug('lipreal thread stop')

        infer_quit_event.set()
        infer_thread.join()

        process_quit_event.set()
        process_thread.join()
        # 停止并等待指标线程退出
        try:
            self._metrics_running = False
        except Exception:
            pass
        try:
            if hasattr(self, '_metrics_thread') and self._metrics_thread is not None:
                self._metrics_thread.join(timeout=1.0)
        except Exception:
            pass
