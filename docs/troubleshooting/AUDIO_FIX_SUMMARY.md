# DoubaoTTS 音频播放和驱动修复总结

## 问题描述

数字人 TTS 播放没声音，且没有驱动口型。

## 根本原因分析

### 1. 音频流向问题

- **DoubaoTTS** 生成音频后调用 `self.parent.put_audio_frame()`
- **BaseReal.put_audio_frame()** 需要同时做两件事：
  1. 转发音频到 **LipASR** (用于口型驱动)
  2. 转发音频到 **WebRTC audio_track** (用于声音播放)

### 2. 原代码问题

```python
# ttsreal.py - DoubaoTTS._push_audio_chunks()
if getattr(self, 'direct_to_webrtc', False):
    self._send_to_webrtc(chunk, eventpoint)  # 直接发送到WebRTC
else:
    self.parent.put_audio_frame(chunk, eventpoint)  # 通过parent转发
```

问题：

- `direct_to_webrtc` 逻辑导致音频要么直接发 WebRTC，要么通过 parent
- 但无论哪种方式，都没有同时转发到 LipASR
- 导致：有声音但无口型，或有口型但无声音

### 3. BaseReal 音频处理问题

```python
# basereal.py - put_audio_frame()
# 原代码在转发给LipASR后，WebRTC转发逻辑有问题
# 1. 队列满时直接丢弃帧
# 2. 音频块大小不匹配时处理不当
```

## 修复方案

### 修复 1: 简化 DoubaoTTS 音频转发

**文件**: `ttsreal.py`

```python
def _push_audio_chunks(self, audio_array, textevent, first_chunk):
    """推送音频块"""
    # ... 省略分块逻辑 ...

    # 🆕 修复：始终调用parent.put_audio_frame，让basereal统一处理音频转发
    self.parent.put_audio_frame(chunk, eventpoint)

def _send_end_event(self, textevent):
    """发送结束事件"""
    # 🆕 修复：始终调用parent.put_audio_frame
    self.parent.put_audio_frame(
        np.zeros(320, dtype=np.float32), eventpoint)
```

**改进**:

- 移除 `direct_to_webrtc` 判断逻辑
- 所有音频统一通过 `parent.put_audio_frame()` 处理
- 由 BaseReal 负责同时转发到 LipASR 和 WebRTC

### 修复 2: 优化 BaseReal 音频处理

**文件**: `basereal.py`

```python
def put_audio_frame(self, audio_chunk, datainfo: dict = {}):
    # 1. 先转发给LipASR（口型驱动）
    if hasattr(self, 'lip_asr'):
        self.lip_asr.put_audio_frame(audio_chunk, datainfo)
        logger.debug(f"[BASE_REAL] Audio forwarded to LipASR")

    # 2. 再转发给WebRTC（声音播放）
    # 音频格式转换
    frame = (audio_chunk * 32767).astype(np.int16)

    # 处理音频块大小不匹配
    if len(frame) != 320:
        if len(frame) < 320:
            # 填充静音而不是丢弃
            padded = np.zeros(320, dtype=np.int16)
            padded[:len(frame)] = frame
            frame = padded
        else:
            # 截取前320个样本
            frame = frame[:320]

    # 创建AudioFrame并发送
    audio_frame = AudioFrame.from_ndarray(...)
    self.audio_track._queue.put_nowait((audio_frame, datainfo))
```

**改进**:

1. **确保 LipASR 转发**: 先转发音频到 LipASR，保证口型驱动
2. **改进音频块处理**:
   - 小于 320 样本时填充静音（而不是丢弃）
   - 大于 320 样本时截取（而不是报错）
3. **优化队列管理**: 提高队列容量阈值到 100（原来是 60）

## 音频流向图

```
DoubaoTTS (生成音频)
    ↓
    txt_to_audio()
    ↓
    _push_audio_chunks()
    ↓
    parent.put_audio_frame()  ← 统一入口
    ↓
BaseReal.put_audio_frame()
    ├─→ LipASR.put_audio_frame()  → 口型驱动
    └─→ WebRTC audio_track        → 声音播放
```

## 测试验证

运行测试脚本：

```bash
python test_audio_fix.py
```

预期结果：

```
✅ 测试通过!
   - 音频正确转发到LipASR (口型驱动)
   - 音频正确发送到WebRTC (声音播放)
```

## 关键改进点

1. **统一音频处理入口**: 所有 TTS 音频都通过 `BaseReal.put_audio_frame()` 处理
2. **双路转发**: 同时转发到 LipASR 和 WebRTC，确保口型和声音都正常
3. **容错处理**: 改进音频块大小不匹配的处理，填充而不是丢弃
4. **日志增强**: 添加详细日志，便于调试

## 影响范围

- ✅ DoubaoTTS: 简化音频转发逻辑
- ✅ BaseReal: 优化音频处理和转发
- ✅ LipASR: 确保接收到音频用于口型驱动
- ✅ WebRTC: 确保音频正确发送用于播放

## 后续建议

1. 监控日志中的音频转发情况
2. 检查队列大小，如果经常超过 100，考虑进一步优化
3. 测试不同文本长度的 TTS 生成
4. 验证音画同步效果
