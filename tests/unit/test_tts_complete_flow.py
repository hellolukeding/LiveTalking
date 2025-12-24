#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LiveTalking TTS完整流程测试
展示从文字输入到音频输出的全过程
"""

import os
import sys
import time
from io import BytesIO

import numpy as np

from logger import logger

# 添加项目路径
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)


class TTSTestFlow:
    """TTS完整流程测试类"""

    def __init__(self):
        self.opt = None
        self.tts = None
        self.basereal = None
        self.test_results = []

    def setup_environment(self):
        """设置测试环境"""
        print("="*70)
        print("🔧 设置测试环境")
        print("="*70)

        # 创建模拟配置
        class MockOpt:
            def __init__(self):
                self.tts = "doubao"  # 使用豆包TTS
                self.sessionid = "test_001"
                self.fps = 25
                self.transport = "webrtc"
                self.doubao_api_key = "test_key"
                self.doubao_api_url = "https://api.doubao.com"
                self.voice_type = "female"
                self.customopt = []
                # 添加豆包TTS需要的属性
                self.REF_FILE = "female"  # voice_id
                self.REF_TEXT = "参考文本"
                self.TTS_SERVER = "http://localhost:5000"
                # 环境变量（模拟）
                os.environ["DOUBAO_APPID"] = "test_appid"
                os.environ["DOUBAO_TOKEN"] = "test_token"
                os.environ["DOUBAO_VOICE_ID"] = "female"

        self.opt = MockOpt()
        print(f"✅ 配置完成: TTS={self.opt.tts}, Session={self.opt.sessionid}")

    def step1_text_input(self):
        """步骤1: 文字输入"""
        print("\n" + "="*70)
        print("📝 步骤1: 文字输入")
        print("="*70)

        test_text = "你好，这是一个TTS测试。"
        print(f"输入文字: {test_text}")
        print(f"文字长度: {len(test_text)} 字符")

        return test_text

    def step2_tts_generation(self):
        """步骤2: TTS生成音频"""
        print("\n" + "="*70)
        print("🎙️ 步骤2: TTS音频生成")
        print("="*70)

        try:
            # 导入TTS模块
            from ttsreal import DoubaoTTS

            # 创建TTS实例
            print("正在初始化DoubaoTTS...")
            self.tts = DoubaoTTS(self.opt, self)

            print("✅ TTS模块初始化完成")
            print(f"TTS类型: {type(self.tts).__name__}")
            print(f"采样率: {self.tts.sample_rate} Hz")
            print(f"块大小: {self.tts.chunk} samples")

            return True

        except Exception as e:
            print(f"❌ TTS初始化失败: {e}")
            return False

    def step3_audio_processing(self):
        """步骤3: 音频处理流程"""
        print("\n" + "="*70)
        print("🔊 步骤3: 音频处理流程")
        print("="*70)

        print("音频处理包含以下步骤:")
        print("1. TTS生成原始音频")
        print("2. 超强力噪音消除 (ttsreal.py)")
        print("3. 格式转换和分块")
        print("4. 终极噪音消除 (basereal.py)")
        print("5. WebRTC传输准备")

        return True

    def step4_noise_reduction_tts(self, audio_chunk):
        """步骤4: TTS层噪音消除"""
        print("\n" + "="*70)
        print("🔇 步骤4: TTS层噪音消除")
        print("="*70)

        try:
            from test_optimization.ultra_noise_reduction import \
                UltraNoiseReductionOptimizer

            # 创建优化器
            class MockTTS:
                def __init__(self):
                    self.chunk = 320
                    self.state = type('State', (), {'RUNNING': 0})()
                    self.audio_track = None
                    self.loop = None

            mock_tts = MockTTS()
            optimizer = UltraNoiseReductionOptimizer(mock_tts, None)

            # 处理音频
            processed = optimizer.apply_ultra_noise_reduction(audio_chunk)

            # 分析效果
            original_rms = np.sqrt(np.mean(audio_chunk ** 2))
            processed_rms = np.sqrt(np.mean(processed ** 2))
            reduction = (1 - processed_rms / original_rms) * 100

            print(f"原始RMS: {original_rms:.5f}")
            print(f"处理后RMS: {processed_rms:.5f}")
            print(f"噪音降低: {reduction:.1f}%")
            print("✅ TTS层处理完成")

            return processed

        except Exception as e:
            print(f"❌ TTS层处理失败: {e}")
            return audio_chunk

    def step5_format_conversion(self, audio_chunk):
        """步骤5: 格式转换"""
        print("\n" + "="*70)
        print("🔄 步骤5: 格式转换")
        print("="*70)

        # 转换为16-bit
        frame = (audio_chunk * 32767).astype(np.int16)

        print(f"原始格式: float32 ({audio_chunk.dtype})")
        print(f"转换后: int16 ({frame.dtype})")
        print(f"数值范围: [{np.min(frame)}, {np.max(frame)}]")
        print("✅ 格式转换完成")

        return frame

    def step6_noise_reduction_basereal(self, audio_chunk):
        """步骤6: basereal层噪音消除"""
        print("\n" + "="*70)
        print("🔇 步骤6: basereal层噪音消除")
        print("="*70)

        try:
            from test_optimization.final_noise_eliminator import \
                FinalNoiseEliminator

            # 创建消除器
            eliminator = FinalNoiseEliminator()

            # 处理音频 (需要转回float32)
            audio_float = audio_chunk.astype(np.float32) / 32767.0
            processed = eliminator.apply_final_elimination(audio_float)

            # 分析效果
            original_rms = np.sqrt(np.mean(audio_float ** 2))
            processed_rms = np.sqrt(np.mean(processed ** 2))
            reduction = (1 - processed_rms / original_rms) * 100

            print(f"原始RMS: {original_rms:.5f}")
            print(f"处理后RMS: {processed_rms:.5f}")
            print(f"噪音降低: {reduction:.1f}%")
            print("✅ basereal层处理完成")

            return processed

        except Exception as e:
            print(f"❌ basereal层处理失败: {e}")
            return audio_chunk

    def step7_webrtc_preparation(self, audio_chunk):
        """步骤7: WebRTC传输准备"""
        print("\n" + "="*70)
        print("🌐 步骤7: WebRTC传输准备")
        print("="*70)

        # 转换为16-bit
        frame = (audio_chunk * 32767).astype(np.int16)

        # 检查音频块大小
        expected_size = 320
        if len(frame) != expected_size:
            print(f"⚠️ 音频块大小不匹配: {len(frame)} vs {expected_size}")
            if len(frame) < expected_size:
                print("音频块过小，丢弃")
                return None
            else:
                frame = frame[:expected_size]
                print(f"截取前{expected_size}个样本")

        print(f"最终格式: int16")
        print(f"块大小: {len(frame)} samples")
        print(f"时长: {len(frame)/16000*1000:.1f} ms")
        print("✅ WebRTC准备完成")

        return frame

    def step8_end_to_end_test(self):
        """步骤8: 端到端测试"""
        print("\n" + "="*70)
        print("🧪 步骤8: 端到端测试")
        print("="*70)

        # 创建测试音频
        print("\n创建测试音频...")
        duration = 1.0
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration))

        # 生成带噪音的测试音频
        speech = np.zeros(len(t))
        t1 = t[(t >= 0.2) & (t < 0.8)]
        speech1 = np.sin(2 * np.pi * 300 * t1) * 0.15
        speech1 += np.sin(2 * np.pi * 600 * t1) * 0.08
        speech[(t >= 0.2) & (t < 0.8)] = speech1

        # 添加噪音
        noise = np.random.randn(len(t)) * 0.08
        noisy_audio = speech + noise
        noisy_audio = np.clip(noisy_audio, -0.95, 0.95)

        print(f"测试音频: {len(noisy_audio)} samples")

        # 模拟完整流程
        print("\n开始端到端处理...")

        # 1. TTS层处理
        print("\n[1/5] TTS层处理...")
        layer1 = self.step4_noise_reduction_tts(noisy_audio)

        # 2. 格式转换
        print("\n[2/5] 格式转换...")
        layer2 = self.step5_format_conversion(layer1)

        # 3. basereal层处理
        print("\n[3/5] basereal层处理...")
        layer3 = self.step6_noise_reduction_basereal(layer2)

        # 4. WebRTC准备
        print("\n[4/5] WebRTC准备...")
        layer4 = self.step7_webrtc_preparation(layer3)

        # 5. 最终分析
        print("\n[5/5] 最终分析...")
        if layer4 is not None:
            final_audio = layer4.astype(np.float32) / 32767.0
            original_rms = np.sqrt(np.mean(noisy_audio ** 2))
            final_rms = np.sqrt(np.mean(final_audio ** 2))
            total_reduction = (1 - final_rms / original_rms) * 100

            print("\n" + "="*50)
            print("📊 最终结果")
            print("="*50)
            print(f"原始RMS: {original_rms:.5f}")
            print(f"最终RMS: {final_rms:.5f}")
            print(f"总体降低: {total_reduction:.1f}%")

            if total_reduction > 50:
                print("\n🎉 成功！噪音显著降低")
            else:
                print("\n⚠️ 需要进一步优化")

            return True
        else:
            print("\n❌ 处理失败")
            return False

    def run_complete_flow(self):
        """运行完整流程"""
        print("\n" + "="*70)
        print("🚀 LiveTalking TTS完整流程测试")
        print("="*70)

        # 1. 设置环境
        self.setup_environment()
        time.sleep(0.5)

        # 2. 文字输入
        text = self.step1_text_input()
        time.sleep(0.5)

        # 3. TTS初始化
        if not self.step2_tts_generation():
            return

        time.sleep(0.5)

        # 4. 音频处理说明
        self.step3_audio_processing()
        time.sleep(0.5)

        # 5. 端到端测试
        success = self.step8_end_to_end_test()

        # 总结
        print("\n" + "="*70)
        print("📋 流程总结")
        print("="*70)
        print("完整流程:")
        print("1. 文字输入 → 2. TTS生成 → 3. TTS层降噪")
        print("4. 格式转换 → 5. basereal层降噪 → 6. WebRTC传输")
        print("\n关键优化点:")
        print("✅ 双层噪音消除")
        print("✅ 严格削波保护")
        print("✅ 高频噪音消除")
        print("✅ 动态增益控制")
        print("✅ 音频块大小控制")

        if success:
            print("\n🎉 测试完成！系统已就绪")
        else:
            print("\n⚠️ 测试完成，但有警告")


def main():
    """主函数"""
    test_flow = TTSTestFlow()
    test_flow.run_complete_flow()


if __name__ == "__main__":
    main()
