#!/usr/bin/env python3
"""
 测试修复后的豆包TTS实现
"""
import base64
import os
import sys
import time
import uuid
from enum import Enum

import numpy as np
import requests
from dotenv import load_dotenv

from logger import logger
from ttsreal import BaseTTS


class State(Enum):
    RUNNING = 0
    PAUSE = 1


# 添加项目路径
sys.path.append('.')

# 从ttsreal中只导入需要的类和函数


class DoubaoTTS(BaseTTS):
    """修复后的豆包TTS类"""

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        # 从配置中读取火山引擎参数
        self.appid = os.getenv("DOUBAO_APPID")
        self.token = os.getenv("DOUBAO_TOKEN")
        # 从环境变量读取voice_id，如果不存在则使用opt.REF_FILE作为fallback
        self.voice_id = os.getenv("DOUBAO_VOICE_ID") or opt.REF_FILE
        _host = "openspeech.bytedance.com"
        self.api_url = f"https://{_host}/api/v1/tts"

    def doubao_voice(self, text):
        """使用HTTP POST方式调用豆包TTS"""
        start = time.perf_counter()

        # 构建请求 - 使用正确的格式
        request_json = {
            "app": {
                "appid": self.appid,
                "token": self.token,
                "cluster": "volcano_tts"
            },
            "user": {
                "uid": str(uuid.uuid4())
            },
            "audio": {
                "voice_type": self.voice_id,
                "encoding": "wav",
                "rate": 16000,
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query"
            }
        }

        logger.debug(f"[DOUBAO_TTS] HTTP POST请求: {self.api_url}")
        logger.info(
            f"[DOUBAO_TTS] AppID: {self.appid}, VoiceID: {self.voice_id}")

        try:
            # 发送HTTP POST请求
            response = requests.post(
                self.api_url,
                json=request_json,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            end = time.perf_counter()
            logger.debug(f"[DOUBAO_TTS] 请求耗时: {end-start:.2f}s")

            if response.status_code == 200:
                result = response.json()

                # 检查响应状态
                if result.get("code", 0) != 3000:
                    logger.error(
                        f"[DOUBAO_TTS] API错误: code={result.get('code')}, message={result.get('message', 'Unknown error')}")
                    return None

                # 获取base64音频数据 - 支持两种格式
                audio_base64 = None
                if "data" in result:
                    if isinstance(result["data"], dict):
                        audio_base64 = result["data"].get("audio")
                    elif isinstance(result["data"], str):
                        audio_base64 = result["data"]

                if not audio_base64:
                    logger.error(f"[DOUBAO_TTS] 响应中没有音频数据: {result}")
                    return None

                # 解码base64
                try:
                    audio_bytes = base64.b64decode(audio_base64)
                    logger.info(
                        f"[DOUBAO_TTS] 收到音频数据: {len(audio_bytes)} bytes")
                    return audio_bytes
                except Exception as e:
                    logger.error(f"[DOUBAO_TTS] Base64解码失败: {e}")
                    return None

            else:
                logger.error(
                    f"[DOUBAO_TTS] HTTP错误 {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"[DOUBAO_TTS] 请求异常: {e}")
            return None

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        logger.debug(f"[DOUBAO_TTS] Starting text_to_audio for: '{text}'")
        logger.info(
            f"[DOUBAO_TTS] AppID: {self.appid}, VoiceID: {self.voice_id}")

        # 调用HTTP接口获取音频
        audio_bytes = self.doubao_voice(text)

        if audio_bytes is None:
            logger.error("[DOUBAO_TTS] 音频生成失败")
            # 发送静音帧避免阻塞
            self.parent.put_audio_frame(
                np.zeros(self.chunk, np.float32), {'status': 'error', 'text': text, 'error': 'TTS请求失败'})
            return

        try:
            # 将音频字节转换为numpy数组
            audio_array = np.frombuffer(
                audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0

            logger.debug(f"[DOUBAO_TTS] 音频数组形状: {audio_array.shape}")

            # 重采样（如果需要）
            # 豆包返回的通常是16kHz，与我们的需求一致，所以可能不需要重采样

            # 流式处理音频
            self.stream_audio(audio_array, msg)

            logger.debug(f"[DOUBAO_TTS] Completed text_to_audio for: '{text}'")

        except Exception as e:
            logger.error(f"[DOUBAO_TTS] 音频处理失败: {e}")
            self.parent.put_audio_frame(
                np.zeros(self.chunk, np.float32), {'status': 'error', 'text': text, 'error': str(e)})

    def stream_audio(self, audio_array, msg: tuple[str, dict]):
        """将完整的音频数组流式发送给父类"""
        text, textevent = msg
        streamlen = audio_array.shape[0]
        idx = 0
        first = True

        logger.debug(f"[DOUBAO_TTS] 开始流式传输音频，总长度: {streamlen}")

        while streamlen >= self.chunk and self.state == State.RUNNING:
            eventpoint = {}

            if first:
                eventpoint = {'status': 'start', 'text': text}
                eventpoint.update(**textevent)
                first = False

            # 发送音频块
            self.parent.put_audio_frame(
                audio_array[idx:idx + self.chunk], eventpoint)

            streamlen -= self.chunk
            idx += self.chunk

            # 小延迟，避免处理过快
            time.sleep(0.001)

        # 发送结束事件
        eventpoint = {'status': 'end', 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32), eventpoint)

        logger.debug(f"[DOUBAO_TTS] 流式传输完成")


class MockOpt:
    """模拟opt参数"""

    def __init__(self):
        self.fps = 50  # 20ms per frame
        self.REF_FILE = 'zh_female_xiaohe_uranus_bigtts'
        self.sessionid = 'test'


class MockParent:
    """模拟父类"""

    def __init__(self):
        self.frames = []
        self.frame_count = 0

    def put_audio_frame(self, audio_chunk, datainfo=None):
        """接收音频帧"""
        self.frame_count += 1
        self.frames.append((audio_chunk.copy(), datainfo))
        if self.frame_count <= 5:  # 只打印前5个
            logger.info(
                f"接收音频帧 {self.frame_count}: shape={audio_chunk.shape}, info={datainfo}")


def test_doubao_tts():
    """测试豆包TTS"""
    print("=" * 60)
    print("测试修复后的豆包TTS实现")
    print("=" * 60)

    # 加载环境变量
    load_dotenv()

    # 检查配置
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv("DOUBAO_VOICE_ID", "zh_female_xiaohe_uranus_bigtts")

    if not appid or not token:
        print("❌ 请在.env文件中配置 DOUBAO_APPID 和 DOUBAO_TOKEN")
        return False

    print(f"✅ 配置检查通过")
    print(f"   AppID: {appid}")
    print(f"   VoiceID: {voice_id}")

    # 创建测试对象
    opt = MockOpt()
    parent = MockParent()

    try:
        # 创建TTS实例
        print("\n🔄 创建DoubaoTTS实例...")
        tts = DoubaoTTS(opt, parent)
        print(f"✅ DoubaoTTS实例创建成功")
        print(f"   API URL: {tts.api_url}")
        print(f"   AppID: {tts.appid}")
        print(f"   VoiceID: {tts.voice_id}")

        # 测试文本
        test_text = "你好，世界！"
        print(f"\n🔄 测试文本: '{test_text}'")

        # 创建消息
        msg = (test_text, {'test': True})

        # 调用txt_to_audio
        print("\n🔄 调用txt_to_audio...")
        start_time = time.time()
        tts.txt_to_audio(msg)
        elapsed = time.time() - start_time

        print(f"\n✅ 测试完成！耗时: {elapsed:.2f}s")
        print(f"   接收音频帧数: {parent.frame_count}")

        if parent.frame_count > 0:
            print(f"   音频数据总量: {sum(len(f[0]) for f in parent.frames)} 样本")

            # 检查音频质量
            all_audio = np.concatenate(
                [f[0] for f in parent.frames]) if parent.frames else np.array([])
            if len(all_audio) > 0:
                print(f"   音频时长: {len(all_audio) / 16000:.2f}s")
                print(
                    f"   音频范围: [{all_audio.min():.3f}, {all_audio.max():.3f}]")
                print(f"   音频均值: {all_audio.mean():.6f}")

                # 检查是否有静音
                silent_frames = np.sum(np.abs(all_audio) < 0.01)
                print(
                    f"   静音样本数: {silent_frames}/{len(all_audio)} ({100*silent_frames/len(all_audio):.1f}%)")

            # 检查事件信息
            events = [f[1] for f in parent.frames if f[1]]
            if events:
                print(f"\n📊 事件信息:")
                for i, event in enumerate(events[:5]):  # 只显示前5个
                    print(f"   事件 {i+1}: {event}")

            return True
        else:
            print("❌ 没有接收到音频帧")
            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_doubao_tts()
    sys.exit(0 if success else 1)
