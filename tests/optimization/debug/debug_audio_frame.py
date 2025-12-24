#!/usr/bin/env python3
"""
调试AudioFrame的samples属性
"""

import numpy as np
from av import AudioFrame

# 创建一个320样本的音频帧
audio_data = np.zeros((1, 320), dtype=np.int16)
frame = AudioFrame.from_ndarray(audio_data, layout='mono', format='s16')

print(f"AudioFrame创建测试:")
print(f"  数据形状: {audio_data.shape}")
print(f"  frame.samples: {getattr(frame, 'samples', '未设置')}")
print(f"  frame.layout: {frame.layout}")
print(f"  frame.format: {frame.format}")
print(f"  frame.sample_rate: {getattr(frame, 'sample_rate', '未设置')}")

# 手动设置sample_rate
frame.sample_rate = 16000
print(f"\n设置sample_rate后:")
print(f"  frame.sample_rate: {frame.sample_rate}")

# 计算samples
if hasattr(frame, 'samples'):
    n_samples = frame.samples
else:
    # 根据数据形状计算
    n_samples = frame.planes[0].samples if hasattr(
        frame.planes[0], 'samples') else frame.data.shape[1]

print(f"  计算的samples: {n_samples}")

# 模拟WebRTC中的处理
sample_rate = getattr(frame, 'sample_rate', 16000)
n_samples = int(getattr(frame, 'samples', 0.020 * sample_rate))
print(f"\nWebRTC处理模拟:")
print(f"  sample_rate: {sample_rate}")
print(f"  n_samples: {n_samples}")
print(f"  预期时长: {n_samples/sample_rate:.3f}s")

# 检查AudioFrame的内部结构
print(f"\nAudioFrame内部结构:")
print(f"  dir(frame): {[x for x in dir(frame) if not x.startswith('_')]}")
