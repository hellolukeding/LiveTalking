# DoubaoTTS 音频问题修复部署指南

## 🎯 问题概述

您遇到的 DoubaoTTS 音频问题包括：

1. **噪音太大** - 音频中存在背景噪音
2. **部分语音丢失** - 长对话中语句不完整
3. **音画不同步** - 声音与数字人嘴形不同步
4. **唇形驱动失效** - 数字人嘴形不动

## 🔧 解决方案

我们提供了**三层优化方案**，可根据需要选择：

### 方案 1：基础音频质量优化

**文件**: `fixes/audio_quality_fix.py`

**功能**:

- ✅ 降噪处理
- ✅ 音量增益控制
- ✅ 静音过滤
- ✅ 削波预防

**使用方法**:

```python
from fixes.audio_quality_fix import apply_audio_quality_optimization

# 在DoubaoTTS初始化后应用
tts = DoubaoTTS()
optimizer = apply_audio_quality_optimization(tts)
```

### 方案 2：消息完整性优化

**文件**: `fixes/optimize_doubao_playback.py`

**功能**:

- ✅ 长文本自动分割
- ✅ 双路音频输出（WebRTC + 唇形驱动）
- ✅ 队列监控保护
- ✅ 消息丢失预防

**使用方法**:

```python
from fixes.optimize_doubao_playback import apply_optimization

# 应用优化
optimizer = apply_optimization(tts, lip_asr)
```

### 方案 3：综合优化（推荐）

**文件**: `fixes/combined_optimization.py`

**功能**: 整合所有优化，解决所有问题

- ✅ 音频质量优化
- ✅ 消息完整性保障
- ✅ 唇形驱动修复
- ✅ 音画同步优化

**使用方法**:

```python
from fixes.combined_optimization import apply_combined_optimization

# 应用综合优化
optimizer = apply_combined_optimization(tts, lip_asr)
```

## 📋 部署步骤

### 步骤 1：文件准备

将以下文件复制到项目目录：

```
fixes/
├── audio_quality_fix.py
├── optimize_doubao_playback.py
├── combined_optimization.py
└── DEPLOYMENT_GUIDE.md
```

### 步骤 2：集成到 DoubaoTTS

**方法 A：自动集成（推荐）**

修改 `ttsreal.py` 中的 `DoubaoTTS` 类：

```python
class DoubaoTTS:
    def __init__(self, ...):
        # ... 原有代码 ...

        # 添加优化器
        self.optimizer = None

    def render(self, text, textevent):
        # ... 原有代码 ...

        # 自动应用优化
        if self.optimizer is None:
            from fixes.combined_optimization import apply_combined_optimization
            self.optimizer = apply_combined_optimization(self, self.parent.lip_asr)

        # ... 继续原有流程 ...
```

**方法 B：手动集成**

在系统初始化时应用优化：

```python
# 在系统启动时
from ttsreal import DoubaoTTS
from fixes.combined_optimization import apply_combined_optimization

tts = DoubaoTTS()
optimizer = apply_combined_optimization(tts, lip_asr_instance)
```

### 步骤 3：验证部署

运行测试验证优化效果：

```bash
poetry run python test_audio_quality.py
poetry run python test_optimization_final.py
```

## 🎛️ 配置参数

### 音频质量配置

```python
optimizer.quality_config = {
    'gain_factor': 1.5,           # 音量增益倍数
    'noise_threshold': 0.008,     # 噪音检测阈值
    'silence_threshold': 0.003,   # 静音检测阈值
    'max_amplitude': 0.90,        # 最大振幅限制
    'enable_denoise': True,       # 启用降噪
    'enable_gain_control': True,  # 启用增益
    'enable_silence_filter': True # 启用静音过滤
}
```

### 缓冲区配置

```python
optimizer.buffer_config = {
    'max_size': 200,      # 缓冲区大小
    'chunk_size': 320,    # 音频块大小
    'enable_direct_forward': True  # 直接转发
}
```

## 📊 监控和调试

### 查看优化状态

```python
status = optimizer.get_status_report()
print(f"WebRTC帧数: {status['stats']['webrtc_frames']}")
print(f"唇形驱动帧数: {status['stats']['lip_driven_frames']}")
print(f"丢失帧数: {status['stats']['lost_frames']}")
print(f"降噪次数: {status['stats']['noise_filtered']}")
```

### 日志输出

优化器会输出详细日志：

```
[COMBINED] 设置综合转发路径
[COMBINED] LipASR就绪
[COMBINED] 音频轨道就绪
[COMBINED] 长文本分割: 200字符 -> 2块
[COMBINED] 流处理完成: 250帧, 耗时0.15s
[COMBINED] WebRTC: 250帧, LipASR: 250帧
[COMBINED] 丢失: 0帧, 降噪: 1200
```

## 🔍 故障排除

### 问题 1：噪音仍然很大

**解决方案**:

```python
# 调整降噪参数
optimizer.quality_config['noise_threshold'] = 0.005  # 更严格
optimizer.quality_config['gain_factor'] = 2.0        # 更强增益
```

### 问题 2：语音仍然丢失

**解决方案**:

```python
# 增大缓冲区
optimizer.buffer_config['max_size'] = 300

# 检查队列状态
status = optimizer.get_status_report()
if status['stats']['lost_frames'] > 0:
    print("警告: 仍有帧丢失，考虑增大缓冲区")
```

### 问题 3：唇形驱动仍然失效

**解决方案**:

```python
# 验证LipASR连接
if not optimizer.lip_asr_ready:
    print("错误: LipASR未就绪")
    # 检查parent.lip_asr是否存在
```

### 问题 4：音画不同步

**解决方案**:

```python
# 减少缓冲区大小降低延迟
optimizer.buffer_config['max_size'] = 100

# 检查音频轨道
if not optimizer.audio_track_ready:
    print("错误: 音频轨道未就绪")
```

## 📈 性能指标

优化后的预期效果：

| 指标       | 优化前 | 优化后   |
| ---------- | ------ | -------- |
| 噪音水平   | 高     | 低       |
| 音量大小   | 小     | 正常     |
| 语音完整性 | 50-80% | 95%+     |
| 唇形驱动   | 失效   | 正常     |
| 音画同步   | 不同步 | 基本同步 |
| 丢失帧率   | 10-30% | <5%      |

## 🚀 生产环境建议

1. **逐步部署**: 先在测试环境验证，再生产环境部署
2. **监控指标**: 持续监控音频质量和丢失率
3. **参数调优**: 根据实际场景调整参数
4. **日志记录**: 保持详细日志用于问题排查

## 📞 技术支持

如遇到问题，请提供：

1. 完整日志输出
2. `optimizer.get_status_report()` 的结果
3. 使用的音频文本示例
4. 系统配置信息

---

**版本**: 1.0  
**更新时间**: 2025-12-24  
**适用版本**: LiveTalking + DoubaoTTS
