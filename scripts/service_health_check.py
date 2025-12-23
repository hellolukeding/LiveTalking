#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务健康检查模块
用于在项目启动前检测ASR和TTS服务的可用性
"""

import json
import os
import sys
import time
from typing import Dict, List, Tuple

import requests
from dotenv import load_dotenv

from logger import logger

# 加载环境变量
load_dotenv()

# 导入日志配置


class ServiceHealthChecker:
    """服务健康检查器"""

    def __init__(self):
        self.results = {}

    def check_all(self) -> bool:
        """检查所有服务"""
        logger.info("=" * 60)
        logger.info("🚀 开始服务健康检查")
        logger.info("=" * 60)

        # 检查TTS服务
        tts_ok = self.check_tts_services()

        # 检查ASR服务
        asr_ok = self.check_asr_services()

        # 检查其他关键配置
        config_ok = self.check_config()

        logger.info("=" * 60)
        logger.info("📊 健康检查结果汇总")
        logger.info("=" * 60)

        all_ok = tts_ok and asr_ok and config_ok

        if all_ok:
            logger.info("✅ 所有服务健康检查通过")
        else:
            logger.error("❌ 部分服务检查失败，请检查配置")

        return all_ok

    def check_tts_services(self) -> bool:
        """检查TTS服务"""
        logger.info("\n🔊 检查TTS服务...")

        tts_type = os.getenv("TTS_TYPE", "edge")
        logger.info(f"当前配置的TTS类型: {tts_type}")

        success_count = 0
        total_count = 0

        # 根据配置的TTS类型进行检查
        if tts_type == "doubao":
            total_count += 1
            if self.check_doubao_tts():
                success_count += 1

        elif tts_type == "edge":
            total_count += 1
            if self.check_edge_tts():
                success_count += 1

        elif tts_type == "tencent":
            total_count += 1
            if self.check_tencent_tts():
                success_count += 1

        elif tts_type == "azure":
            total_count += 1
            if self.check_azure_tts():
                success_count += 1

        elif tts_type == "fish":
            total_count += 1
            if self.check_fish_tts():
                success_count += 1

        elif tts_type == "sovits":
            total_count += 1
            if self.check_sovits_tts():
                success_count += 1

        elif tts_type == "cosyvoice":
            total_count += 1
            if self.check_cosyvoice_tts():
                success_count += 1

        elif tts_type == "indextts2":
            total_count += 1
            if self.check_indextts2_tts():
                success_count += 1

        elif tts_type == "xtts":
            total_count += 1
            if self.check_xtts_tts():
                success_count += 1

        # 检查所有TTS服务（可选）
        logger.info("\n📋 可选：检查所有TTS服务...")
        all_tts_services = [
            ("Edge TTS", self.check_edge_tts),
            ("豆包 TTS", self.check_doubao_tts),
            ("腾讯 TTS", self.check_tencent_tts),
            ("Azure TTS", self.check_azure_tts),
            ("Fish TTS", self.check_fish_tts),
            ("Sovits TTS", self.check_sovits_tts),
            ("CosyVoice TTS", self.check_cosyvoice_tts),
            ("IndexTTS2", self.check_indextts2_tts),
            ("XTTS", self.check_xtts_tts),
        ]

        for name, check_func in all_tts_services:
            if check_func():
                logger.info(f"  ✅ {name}: 可用")
            else:
                logger.warning(f"  ❌ {name}: 不可用或未配置")

        return success_count > 0

    def check_asr_services(self) -> bool:
        """检查ASR服务"""
        logger.info("\n🎤 检查ASR服务...")

        asr_type = os.getenv("ASR_TYPE", "funasr")
        logger.info(f"当前配置的ASR类型: {asr_type}")

        success_count = 0
        total_count = 0

        # 根据配置的ASR类型进行检查
        if asr_type == "tencent":
            total_count += 1
            if self.check_tencent_asr():
                success_count += 1

        elif asr_type == "funasr":
            total_count += 1
            if self.check_funasr_asr():
                success_count += 1

        elif asr_type == "huber":
            total_count += 1
            if self.check_huber_asr():
                success_count += 1

        elif asr_type == "lip":
            total_count += 1
            if self.check_lip_asr():
                success_count += 1

        # 检查所有ASR服务（可选）
        logger.info("\n📋 可选：检查所有ASR服务...")
        all_asr_services = [
            ("腾讯 ASR", self.check_tencent_asr),
            ("FunASR", self.check_funasr_asr),
            ("Huber ASR", self.check_huber_asr),
            ("Lip ASR", self.check_lip_asr),
        ]

        for name, check_func in all_asr_services:
            if check_func():
                logger.info(f"  ✅ {name}: 可用")
            else:
                logger.warning(f"  ❌ {name}: 不可用或未配置")

        return success_count > 0

    def check_config(self) -> bool:
        """检查关键配置"""
        logger.info("\n⚙️  检查关键配置...")

        config_items = [
            ("TTS_TYPE", os.getenv("TTS_TYPE")),
            ("ASR_TYPE", os.getenv("ASR_TYPE")),
            ("FPS", os.getenv("FPS", "20")),
            ("LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")),
        ]

        all_ok = True
        for name, value in config_items:
            if value:
                logger.info(f"  ✅ {name}: {value}")
            else:
                logger.warning(f"  ⚠️  {name}: 未设置")
                if name in ["TTS_TYPE", "ASR_TYPE"]:
                    all_ok = False

        return all_ok

    # ==================== TTS 服务检查 ====================

    def check_edge_tts(self) -> bool:
        """检查Edge TTS"""
        try:
            import asyncio

            import edge_tts

            # 尝试获取可用语音列表
            async def get_voices():
                voices = await edge_tts.list_voices()
                return voices

            voices = asyncio.run(get_voices())
            if voices and len(voices) > 0:
                logger.info(f"  Edge TTS: 可用，找到 {len(voices)} 个语音")
                return True
            else:
                logger.warning("  Edge TTS: 未找到可用语音")
                return False
        except Exception as e:
            logger.error(f"  Edge TTS 检查失败: {e}")
            return False

    def check_doubao_tts(self) -> bool:
        """检查豆包TTS"""
        appid = os.getenv("DOUBAO_APPID")
        token = os.getenv("DOUBAO_TOKEN")
        voice_id = os.getenv("DOUBAO_VOICE_ID")

        if not all([appid, token, voice_id]):
            logger.warning("  豆包TTS: 缺少配置参数")
            return False

        try:
            # 测试API连接
            url = "https://openspeech.bytedance.com/api/v1/tts"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "app": {
                    "appid": appid,
                    "token": "access_token",
                    "cluster": "volcano_tts"
                },
                "user": {
                    "uid": "test_health_check"
                },
                "audio": {
                    "voice_type": voice_id,
                    "encoding": "pcm",
                    "rate": 16000
                },
                "request": {
                    "reqid": str(int(time.time())),
                    "text": "测试",
                    "text_type": "plain",
                    "operation": "submit"
                }
            }

            response = requests.post(
                url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                logger.info("  豆包TTS: API连接正常")
                return True
            elif response.status_code == 401:
                logger.error("  豆包TTS: 认证失败，请检查Token")
                return False
            else:
                logger.warning(f"  豆包TTS: API返回状态码 {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"  豆包TTS 检查失败: {e}")
            return False

    def check_tencent_tts(self) -> bool:
        """检查腾讯TTS"""
        appid = os.getenv("TENCENT_APPID")
        secret_id = os.getenv("TENCENT_SECRET_ID")
        secret_key = os.getenv("TENCENT_SECRET_KEY")

        if not all([appid, secret_id, secret_key]):
            logger.warning("  腾讯TTS: 缺少配置参数")
            return False

        try:
            # 简单的参数验证
            logger.info("  腾讯TTS: 配置参数完整")
            return True
        except Exception as e:
            logger.error(f"  腾讯TTS 检查失败: {e}")
            return False

    def check_azure_tts(self) -> bool:
        """检查Azure TTS"""
        speech_key = os.getenv("AZURE_SPEECH_KEY")
        tts_region = os.getenv("AZURE_TTS_REGION")

        if not all([speech_key, tts_region]):
            logger.warning("  Azure TTS: 缺少配置参数")
            return False

        try:
            # 简单的参数验证
            logger.info("  Azure TTS: 配置参数完整")
            return True
        except Exception as e:
            logger.error(f"  Azure TTS 检查失败: {e}")
            return False

    def check_fish_tts(self) -> bool:
        """检查Fish TTS"""
        tts_server = os.getenv("TTS_SERVER")

        if not tts_server:
            logger.warning("  Fish TTS: 缺少TTS_SERVER配置")
            return False

        try:
            # 测试服务器连接
            test_url = f"{tts_server}/v1/tts"
            response = requests.get(test_url, timeout=5)

            if response.status_code in [200, 405]:  # 405表示接口存在但方法不对
                logger.info("  Fish TTS: 服务器连接正常")
                return True
            else:
                logger.warning(f"  Fish TTS: 服务器返回状态码 {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"  Fish TTS 检查失败: {e}")
            return False

    def check_sovits_tts(self) -> bool:
        """检查Sovits TTS"""
        tts_server = os.getenv("TTS_SERVER")

        if not tts_server:
            logger.warning("  Sovits TTS: 缺少TTS_SERVER配置")
            return False

        try:
            # 测试服务器连接
            test_url = f"{tts_server}/tts"
            response = requests.get(test_url, timeout=5)

            if response.status_code in [200, 405]:
                logger.info("  Sovits TTS: 服务器连接正常")
                return True
            else:
                logger.warning(
                    f"  Sovits TTS: 服务器返回状态码 {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"  Sovits TTS 检查失败: {e}")
            return False

    def check_cosyvoice_tts(self) -> bool:
        """检查CosyVoice TTS"""
        tts_server = os.getenv("TTS_SERVER")

        if not tts_server:
            logger.warning("  CosyVoice TTS: 缺少TTS_SERVER配置")
            return False

        try:
            # 测试服务器连接
            test_url = f"{tts_server}/inference_zero_shot"
            response = requests.get(test_url, timeout=5)

            if response.status_code in [200, 405]:
                logger.info("  CosyVoice TTS: 服务器连接正常")
                return True
            else:
                logger.warning(
                    f"  CosyVoice TTS: 服务器返回状态码 {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"  CosyVoice TTS 检查失败: {e}")
            return False

    def check_indextts2_tts(self) -> bool:
        """检查IndexTTS2"""
        tts_server = os.getenv("TTS_SERVER")

        if not tts_server:
            logger.warning("  IndexTTS2: 缺少TTS_SERVER配置")
            return False

        try:
            from gradio_client import Client

            # 尝试连接Gradio客户端
            client = Client(tts_server)
            logger.info("  IndexTTS2: Gradio客户端连接正常")
            return True

        except ImportError:
            logger.warning("  IndexTTS2: 未安装 gradio_client")
            return False
        except Exception as e:
            logger.error(f"  IndexTTS2 检查失败: {e}")
            return False

    def check_xtts_tts(self) -> bool:
        """检查XTTS"""
        tts_server = os.getenv("TTS_SERVER")

        if not tts_server:
            logger.warning("  XTTS: 缺少TTS_SERVER配置")
            return False

        try:
            # 测试克隆说话人接口
            test_url = f"{tts_server}/clone_speaker"
            response = requests.get(test_url, timeout=5)

            if response.status_code in [200, 405]:
                logger.info("  XTTS: 服务器连接正常")
                return True
            else:
                logger.warning(f"  XTTS: 服务器返回状态码 {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"  XTTS 检查失败: {e}")
            return False

    # ==================== ASR 服务检查 ====================

    def check_tencent_asr(self) -> bool:
        """检查腾讯ASR"""
        appid = os.getenv("TENCENT_APPID")
        secret_id = os.getenv("TENCENT_SECRET_ID")
        secret_key = os.getenv("TENCENT_SECRET_KEY")

        if not all([appid, secret_id, secret_key]):
            logger.warning("  腾讯ASR: 缺少配置参数")
            return False

        try:
            # 简单的参数验证
            logger.info("  腾讯ASR: 配置参数完整")
            return True
        except Exception as e:
            logger.error(f"  腾讯ASR 检查失败: {e}")
            return False

    def check_funasr_asr(self) -> bool:
        """检查FunASR"""
        try:
            # 检查是否安装了funasr
            import funasr
            logger.info("  FunASR: 已安装")
            return True
        except ImportError:
            logger.warning("  FunASR: 未安装")
            return False
        except Exception as e:
            logger.error(f"  FunASR 检查失败: {e}")
            return False

    def check_huber_asr(self) -> bool:
        """检查Huber ASR"""
        try:
            # 检查相关模块
            from hubertasr import HuberASR
            logger.info("  Huber ASR: 模块可用")
            return True
        except ImportError:
            logger.warning("  Huber ASR: 模块不可用")
            return False
        except Exception as e:
            logger.error(f"  Huber ASR 检查失败: {e}")
            return False

    def check_lip_asr(self) -> bool:
        """检查Lip ASR"""
        try:
            # 检查相关模块
            from lipasr import LipASR
            logger.info("  Lip ASR: 模块可用")
            return True
        except ImportError:
            logger.warning("  Lip ASR: 模块不可用")
            return False
        except Exception as e:
            logger.error(f"  Lip ASR 检查失败: {e}")
            return False


def main():
    """主函数"""
    checker = ServiceHealthChecker()
    success = checker.check_all()

    if success:
        print("\n✅ 健康检查通过，可以启动项目")
        sys.exit(0)
    else:
        print("\n❌ 健康检查失败，请检查配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
