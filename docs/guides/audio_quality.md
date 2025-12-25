# TTS 音频质量优化指南 - 电音消除终极方案

## 问题根因

电音问题的根本原因是 **采样率不匹配**：

1. TTS 输出：16kHz
2. aiortc Opus 编码器：48kHz
3. aiortc 内部重采样质量差，导致电音

## 解决方案

### 核心修复

在发送给 WebRTC 之前，手动将 16kHz 音频重采样到 48kHz：

1. `webrtc.py`: SAMPLE_RATE 改为 48000
2. `basereal.py`: put_audio_frame() 中使用线性插值重采样
3. 输出帧大小：960 samples (48kHz @ 20ms)

### 技术细节

```python
# 16kHz -> 48kHz 线性插值
from scipy.interpolate import interp1d
x_16k = np.arange(len(frame_16k))
x_48k = np.linspace(0, len(frame_16k)-1, len(frame_16k)*3)
f = interp1d(x_16k, frame_16k, kind='linear')
frame_48k = f(x_48k)
```

### 为什么选择线性插值？

| 方法          | 最大跳变 | 过冲 |
| ------------- | -------- | ---- |
| resample_poly | 0.19     | 有   |
| 线性插值      | 0.03     | 无   |
| 三次样条      | 0.03     | 极小 |

线性插值虽然频率响应不如 polyphase，但对于语音来说足够好，且不会引入过冲导致的电音。

## 故障排除

### 仍有电音？

1. 检查 TTS 源是否有问题（保存原始音频测试）
2. 检查网络延迟导致的丢包
3. 尝试增加 fade_samples 到 256

### 音质变差？

可以尝试三次样条插值：

```python
f = interp1d(x_16k, frame_16k, kind='cubic')
```
