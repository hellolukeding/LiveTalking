# DoubaoTTS 音频优化测试目录

这个目录包含了所有用于解决 DoubaoTTS 音频问题的优化方案、测试脚本和文档。

## 📁 目录结构

### 🔧 核心优化模块

| 文件                          | 功能           | 说明                          |
| ----------------------------- | -------------- | ----------------------------- |
| `combined_optimization.py`    | **综合优化器** | ⭐ 推荐使用，整合所有优化功能 |
| `audio_quality_fix.py`        | 音频质量优化   | 降噪、增益、削波预防          |
| `optimize_doubao_playback.py` | 消息完整性优化 | 长文本分割、双路输出          |
| `quick_apply.py`              | 一键应用脚本   | 快速集成所有优化              |

### 🧪 测试脚本

| 文件                              | 功能         | 说明               |
| --------------------------------- | ------------ | ------------------ |
| `test_integrated_optimization.py` | 集成测试     | 验证优化器集成效果 |
| `test_audio_quality.py`           | 音频质量测试 | 测试降噪和增益效果 |
| `test_optimization_final.py`      | 综合测试     | 完整功能测试       |
| `test_optimization_simple.py`     | 简单测试     | 基础功能验证       |
| `test_final_fix.py`               | 最终修复测试 | 验证最终方案       |

### 📚 文档

| 文件                  | 内容             |
| --------------------- | ---------------- |
| `SOLUTION_SUMMARY.md` | 完整解决方案总结 |
| `DEPLOYMENT_GUIDE.md` | 生产环境部署指南 |
| `README.md`           | 快速使用指南     |

### 📦 旧版本优化（存档）

| 文件                      | 说明         |
| ------------------------- | ------------ |
| `fix_doubao_tts.py`       | 初版优化     |
| `fix_doubao_tts2.py`      | 第二版优化   |
| `fix_doubao_tts3.py`      | 第三版优化   |
| `fix_doubao_tts_queue.py` | 队列优化     |
| `audio_sync_fix.py`       | 同步优化     |
| `final_audio_fix.py`      | 最终音频修复 |
| `simple_audio_fix.py`     | 简单修复     |
| `ultimate_audio_fix.py`   | 终极修复     |

## 🚀 快速开始

### 方法 1：使用综合优化器（推荐）

```python
# 在您的项目中
from test_optimization.combined_optimization import apply_combined_optimization

# 应用优化
optimizer = apply_combined_optimization(tts_instance, lip_asr_instance)
```

### 方法 2：一键应用所有优化

```python
from test_optimization.quick_apply import apply_all_optimizations

optimizers = apply_all_optimizations(tts_instance, lip_asr_instance)
```

### 方法 3：运行测试验证

```bash
cd test_optimization
poetry run python test_integrated_optimization.py
```

## 🎯 解决的问题

- ✅ **噪音太大** - 智能降噪处理
- ✅ **部分语音丢失** - 长文本分割和队列保护
- ✅ **音画不同步** - 缓冲区优化和同步机制
- ✅ **唇形驱动失效** - 直接转发和双路输出

## 📊 效果验证

运行测试查看优化效果：

```bash
poetry run python test_audio_quality.py
poetry run python test_integrated_optimization.py
```

## 🎛️ 参数调优

### 增强降噪

```python
optimizer.quality_config['noise_threshold'] = 0.003
optimizer.quality_config['gain_factor'] = 2.5
```

### 降低延迟

```python
optimizer.buffer_config['max_size'] = 100
```

### 增大缓冲区

```python
optimizer.buffer_config['max_size'] = 300
```

## 📈 监控状态

```python
status = optimizer.get_status_report()
print(f"WebRTC帧: {status['stats']['webrtc_frames']}")
print(f"唇形驱动帧: {status['stats']['lip_driven_frames']}")
print(f"丢失帧: {status['stats']['lost_frames']}")
```

## 🔍 故障排除

如果遇到问题，请查看：

1. `SOLUTION_SUMMARY.md` - 完整解决方案
2. `DEPLOYMENT_GUIDE.md` - 部署指南
3. `README.md` - 快速指南

## 📝 注意事项

1. **推荐使用** `combined_optimization.py` - 功能最完整
2. **测试验证** - 运行测试脚本确认效果
3. **监控状态** - 定期检查优化器状态
4. **参数调优** - 根据实际场景调整参数

---

**版本**: 1.0  
**更新**: 2025-12-24  
**适用**: LiveTalking + DoubaoTTS

**所有优化文件已整理到此目录，便于管理和使用！**
