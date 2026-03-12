# Wav2Lip256 → Wav2Lip384 迁移计划

## 项目概述

本文档描述了将 LiveTalking 项目从 wav2lip256 模型迁移到 wav2lip384 模型的完整计划。

**目标**: 提升数字人视频输出质量，从 480p 提升到 720p-1080p

**预期收益**:
- 视频分辨率: 256×256 → 384×384 (+50%)
- 输出质量: 支持 720p/1080p/2K/4K 数字人视频
- 口型同步精度: 更高分辨率的面部特征

**资源成本**:
- 显存占用: ~3GB → ~6GB (翻倍)
- 推理延迟: +30-50%
- 推荐GPU: 显存 ≥8GB

---

## 一、当前状态分析

### 1.1 已具备的资源

#### 模型检查点文件
```
/models/wav2lip384/
├── color_checkpoints/
│   ├── checkpoint_step000015000.pth (781MB)
│   ├── checkpoint_step000693000.pth (781MB)
│   └── checkpoint_step001810000.pth (781MB)
└── final_checkpionts/
    ├── checkpoint_step000370000.pth (2.07GB)
    ├── checkpoint_step000690000.pth (2.07GB)
    └── checkpoint_step000760000.pth (2.07GB) ⭐ 推荐
```

#### 参考代码库
```
/refer/wav2lip384x384/
├── models/
│   ├── wav2lip.py      # 核心384模型 (含SAM注意力机制)
│   ├── conv_384.py     # 384专用卷积模块
│   └── syncnet.py      # 同步网络
├── audio.py            # 音频处理
├── hparams.py          # 超参数配置
├── inference.py        # 离线推理脚本
├── inference_realtime.py # 实时推理脚本
├── preprocess.py       # 数据预处理
└── face_detection/     # 人脸检测模块
```

#### 当前项目结构
```
/src/
├── main/app.py         # 主入口 (行890-892需修改)
└── core/lipreal.py     # Wav2Lip推理核心 (行41, 98-103需修改)

/wav2lip/
├── models/             # 需添加384模型定义
├── genavatar.py        # Avatar生成工具 (需支持384)
└── face_detection/     # 已兼容

/data/avatars/
└── wav2lip256_avatar1/ # 需重新生成384版本
```

### 1.2 架构差异对比

| 组件 | wav2lip256 | wav2lip384 |
|------|-----------|-----------|
| 输入分辨率 | 256×256 | 384×384 |
| 特征维度 | 512 | 1024 |
| 编码器层数 | 8层 | 8层 (更深层) |
| 注意力机制 | 无 | SAM (Spatial Attention) |
| 音频编码器输出 | 512 | 1024 |
| 解码器通道数 | 512→256→128→64 | 1024→768→512→256→128→64 |

---

## 二、迁移步骤

### 阶段一: 代码集成 (1-2小时)

#### 步骤 1.1: 复制模型定义文件

```bash
# 创建384模型文件
cp refer/wav2lip384x384/models/wav2lip.py wav2lip/models/wav2lip_384.py
cp refer/wav2lip384x384/models/conv_384.py wav2lip/models/conv_384.py
```

#### 步骤 1.2: 修改 lipreal.py

文件: `src/core/lipreal.py`

**位置 1** - 行 41:
```python
# 修改前
from wav2lip.models.wav2lip_v2 import Wav2Lip

# 修改后
from wav2lip.models.wav2lip_384 import Wav2Lip
```

**位置 2** - 行 98-103 (warm_up函数):
```python
# 修改前
@torch.no_grad()
def warm_up(batch_size, model, modelres):
    logger.debug('warmup model...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)

# 修改后 (保持兼容，modelres 参数化)
@torch.no_grad()
def warm_up(batch_size, model, modelres):  # 256 或 384
    logger.debug(f'warmup model... resolution={modelres}')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)
```

**位置 3** - 行 125-234 (inference函数):

确认 face resize 逻辑能够动态适应:
```python
# 当前代码 (行 183) 已是动态的，无需修改
face = face_list_cycle[idx]
```

#### 步骤 1.3: 修改 app.py

文件: `src/main/app.py`

**位置 1** - 行 890:
```python
# 修改前
model = load_model("./models/wav2lip256.pth")

# 修改后
model = load_model("./models/wav2lip384/final_checkpionts/checkpoint_step000760000.pth")
```

**位置 2** - 行 892:
```python
# 修改前
warm_up(opt.batch_size, model, 256)

# 修改后
warm_up(opt.batch_size, model, 384)
```

**位置 3** - 行 830 (可选，更新默认avatar):
```python
# 修改前
parser.add_argument('--avatar_id', type=str, default='wav2lip256_avatar1',
                    help="define which avatar in data/avatars")

# 修改后 (先生成384 avatar后再改)
parser.add_argument('--avatar_id', type=str, default='wav2lip384_avatar1',
                    help="define which avatar in data/avatars")
```

#### 步骤 1.4: 更新 models/__init__.py

文件: `wav2lip/models/__init__.py`

```python
# 添加384模型导入
from .wav2lip_384 import Wav2Lip as Wav2Lip384
from .wav2lip_v2 import Wav2Lip as Wav2Lip256

__all__ = ['Wav2Lip256', 'Wav2Lip384']
```

---

### 阶段二: Avatar 数据准备 (1-2小时)

#### 步骤 2.1: 修改 genavatar.py 支持384

文件: `wav2lip/genavatar.py`

**位置 1** - 行 13:
```python
# 修改前
parser.add_argument('--img_size', default=96, type=int)

# 修改后
parser.add_argument('--img_size', default=384, type=int,
                    help='Face image size (96 for wav2lip256, 384 for wav2lip384)')
```

**位置 2** - 行 103 (修改输出路径):
```python
# 修改前
avatar_path = f"./results/avatars/{args.avatar_id}"

# 修改后 (统一放到 data/avatars)
avatar_path = f"./data/avatars/{args.avatar_id}"
```

#### 步骤 2.2: 生成384 Avatar

```bash
cd wav2lip

# 准备你的源视频 (建议5-10秒，正面人脸)
# 假设视频路径为 /path/to/your/avatar_video.mp4

python genavatar.py \
    --img_size 384 \
    --avatar_id wav2lip384_avatar1 \
    --video_path /path/to/your/avatar_video.mp4 \
    --pads 0 10 0 0 \
    --face_det_batch_size 16
```

**验证输出**:
```bash
ls -la data/avatars/wav2lip384_avatar1/
# 应包含:
# - coords.pkl      (人脸坐标)
# - face_imgs/      (384x384 人脸图)
# - full_imgs/      (完整帧)
# - meta.json       (元数据)
```

---

### 阶段三: 测试验证 (1小时)

#### 步骤 3.1: 模型加载测试

```bash
cd /opt/2026/LiveTalking

# 测试模型加载
python -c "
from src.core.lipreal import load_model
model = load_model('./models/wav2lip384/final_checkpionts/checkpoint_step000760000.pth')
print('Model loaded successfully!')
print(f'Model type: {type(model)}')
"
```

#### 步骤 3.2: Avatar 加载测试

```bash
python -c "
from src.core.lipreal import load_avatar
frame_list, face_list, coord_list = load_avatar('wav2lip384_avatar1')
print(f'Avatar loaded: {len(face_list)} frames')
print(f'Face shape: {face_list[0].shape}')
"
```

#### 步骤 3.3: 端到端推理测试

```bash
# 启动服务 (使用小batch_size测试)
python src/main/app.py \
    --model wav2lip \
    --avatar_id wav2lip384_avatar1 \
    --batch_size 8 \
    --transport webrtc \
    --listenport 8010
```

**监控指标**:
- 显存占用: `nvidia-smi`
- FPS: 观察日志输出
- 推理延迟: 观察日志中的推理时间

#### 步骤 3.4: 性能基准测试

| 指标 | 目标值 | 测试方法 |
|------|--------|---------|
| 显存占用 | <8GB | nvidia-smi |
| 推理FPS | >15 FPS | 日志统计 |
| 端到端延迟 | <100ms | 体验测试 |

---

### 阶段四: 性能优化 (可选)

#### 优化 4.1: Batch Size 调优

```bash
# 根据显存情况调整 batch_size
# 默认值: 16
# 推荐: 8 (如果显存紧张)
python src/main/app.py --batch_size 8
```

#### 优化 4.2: 模型量化 (可选)

```python
# 在 lipreal.py 的 load_model 中添加
import torch.quantization

model = torch.quantization.quantize_dynamic(
    model, {torch.nn.Linear, torch.nn.Conv2d}, dtype=torch.qint8
)
```

#### 优化 4.3: 推理加速 (可选)

```python
# 使用 torch.compile 加速 (PyTorch 2.0+)
model = torch.compile(model, mode='reduce-overhead')
```

---

## 三、风险评估与缓解

### 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 显存不足 | 中 | 高 | 降低 batch_size 到 8 |
| 性能下降 | 高 | 中 | 优化推理代码，使用 TensorRT |
| Avatar 不兼容 | 低 | 中 | 使用 genavatar.py 重新生成 |
| 模型加载失败 | 低 | 高 | 验证 checkpoint 文件完整性 |

### 回滚计划

如果迁移失败，快速回滚步骤:

```bash
# 1. 恢复代码
git checkout src/core/lipreal.py
git checkout src/main/app.py

# 2. 切换回256模型
# 在 app.py 中修改回:
# model = load_model("./models/wav2lip256.pth")
# warm_up(opt.batch_size, model, 256)

# 3. 使用原avatar
# --avatar_id wav2lip256_avatar1
```

---

## 四、验证清单

### 代码集成检查

- [ ] `wav2lip/models/wav2lip_384.py` 已创建
- [ ] `wav2lip/models/conv_384.py` 已创建
- [ ] `src/core/lipreal.py` 已修改导入
- [ ] `src/main/app.py` 已修改模型路径
- [ ] `wav2lip/models/__init__.py` 已更新

### 数据准备检查

- [ ] `data/avatars/wav2lip384_avatar1/` 目录存在
- [ ] `coords.pkl` 文件存在且有效
- [ ] `face_imgs/` 包含足够数量的384×384图片
- [ ] `full_imgs/` 包含完整帧图片

### 功能验证检查

- [ ] 模型能够成功加载
- [ ] Avatar 能够成功加载
- [ ] 推理服务能够正常启动
- [ ] WebRTC 连接正常
- [ ] 口型同步正常
- [ ] 视频输出质量提升明显

### 性能验证检查

- [ ] 显存占用在可接受范围 (<8GB)
- [ ] FPS 满足实时性要求 (>15 FPS)
- [ ] 延迟在可接受范围 (<100ms)

---

## 五、配置文件模板

### 推荐启动配置

```bash
# 标准配置 (8GB+ 显存)
python src/main/app.py \
    --model wav2lip \
    --avatar_id wav2lip384_avatar1 \
    --batch_size 16 \
    --fps 50 \
    --transport webrtc \
    --listenport 8010 \
    --video_bitrate 3000 \
    --video_codec auto

# 低显存配置 (6GB 显存)
python src/main/app.py \
    --model wav2lip \
    --avatar_id wav2lip384_avatar1 \
    --batch_size 8 \
    --fps 50 \
    --transport webrtc \
    --listenport 8010 \
    --video_bitrate 2000
```

### 环境变量配置

```bash
# .env
TTS_TYPE=edgetts
ASR_TYPE=tencent
TENCENT_ASR_DURATION_MS=1000
ASR_INTERVAL_FRAMES=25
```

---

## 六、时间估算

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| 阶段一 | 代码集成 | 1-2 小时 |
| 阶段二 | Avatar准备 | 1-2 小时 |
| 阶段三 | 测试验证 | 1 小时 |
| 阶段四 | 性能优化 | 1-2 小时 (可选) |
| **总计** | | **4-7 小时** |

---

## 七、参考资料

### 相关文件路径

```
模型检查点:
- /opt/2026/LiveTalking/models/wav2lip384/final_checkpionts/checkpoint_step000760000.pth

参考代码:
- /opt/2026/LiveTalking/refer/wav2lip384x384/

当前项目:
- /opt/2026/LiveTalking/src/core/lipreal.py
- /opt/2026/LiveTalking/src/main/app.py
- /opt/2026/LiveTalking/wav2lip/genavatar.py

文档:
- https://github.com/langzizhixin/wav2lip384x384
```

### 关键差异

1. **SAM 注意力机制**: 384版本新增了空间注意力模块
2. **特征维度翻倍**: 从512提升到1024
3. **更深层的网络**: 编码器和解码器都有更多层
4. **更大显存需求**: 推理时显存占用约翻倍

---

## 八、附录: 快速命令参考

```bash
# === 开发调试 ===

# 1. 测试模型加载
python -c "from src.core.lipreal import load_model; load_model('./models/wav2lip384/final_checkpionts/checkpoint_step000760000.pth')"

# 2. 生成新Avatar
cd wav2lip && python genavatar.py --img_size 384 --avatar_id test_avatar --video_path test.mp4

# 3. 查看显存
watch -n 1 nvidia-smi

# 4. 启动服务
python src/main/app.py --model wav2lip --avatar_id wav2lip384_avatar1 --batch_size 8

# === 故障排查 ===

# 1. 检查模型文件
ls -lh models/wav2lip384/final_checkpionts/

# 2. 检查Avatar结构
ls -la data/avatars/wav2lip384_avatar1/

# 3. 查看日志
tail -f /tmp/livetalking.log

# === 回滚操作 ===

# 恢复原始代码
git checkout src/core/lipreal.py src/main/app.py
```

---

**文档版本**: 1.0
**创建日期**: 2026-03-12
**最后更新**: 2026-03-12
**负责人**: LiveTalking 开发团队
