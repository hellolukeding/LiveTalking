# LiveTalking 依赖管理

## 快速开始

### 一键安装所有依赖

```bash
# 使用安装脚本（推荐）
./scripts/install_deps.sh

# 或使用 pip
pip install -r requirements_full.txt
```

### 检查依赖状态

```bash
python scripts/check_deps.py
```

### 快速修复缺失依赖

```bash
./scripts/fix_deps.sh
```

## 核心依赖分类

### 深度学习框架
- `torch` - PyTorch 核心库
- `torchvision` - 计算机视觉
- `torchaudio` - 音频处理
- `transformers` - Hugging Face 模型
- `diffusers` - 扩散模型
- `accelerate` - 模型加速
- `safetensors` - 安全的张子存储

### WebRTC/音视频
- `aiortc` - WebRTC 实现
- `av` - 音视频编解码
- `opencv-python` - 图像处理
- `soundfile` - 音频文件 I/O
- `librosa` - 音频分析

### TTS (文本转语音)
- `edge_tts` - Microsoft Edge TTS
- `azure-cognitiveservices-speech` - Azure TTS
- `pydub` - 音频格式转换

### ASR (语音识别)
- `httpx` - HTTP 客户端 (Tencent ASR)
- `websockets` - WebSocket 连接 (Doubao TTS)
- `websocket-client` - WebSocket 客户端

### LLM/AI
- `openai` - OpenAI API 客户端
- `socksio` - SOCKS 代理支持

### Web 框架
- `flask` - Web 服务器
- `flask_sockets` - WebSocket 支持
- `gradio_client` - Gradio 客户端

## 常见问题

### 1. ModuleNotFoundError: No module named 'pydub'

**解决方案**:
```bash
pip install pydub
```

### 2. ImportError: Using SOCKS proxy, but the 'socksio' package is not installed

**解决方案**:
```bash
pip install socksio
```

### 3. ffmpeg 相关错误

**解决方案** (Ubuntu/Debian):
```bash
sudo apt-get install ffmpeg
```

**解决方案** (macOS):
```bash
brew install ffmpeg
```

### 4. CUDA 相关问题

确保安装了与 CUDA 版本匹配的 PyTorch:

```bash
# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# CPU 版本
pip install torch torchvision torchaudio
```

## 虚拟环境管理

### 创建虚拟环境
```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows
```

### 导出已安装的包
```bash
pip freeze > requirements_installed.txt
```

### 从已安装的包恢复
```bash
pip install -r requirements_installed.txt
```

## 依赖更新

### 更新所有包
```bash
pip list --outdated
pip install --upgrade <package_name>
```

### 更新 requirements_full.txt
```bash
# 使用 pip-compile (需要 pip-tools)
pip install pip-tools
pip-compile pyproject.toml -o requirements_full.txt
```

## 开发环境设置

### 安装开发依赖
```bash
pip install pytest black flake8 mypy
```

### 运行测试
```bash
pytest tests/
```

### 代码格式化
```bash
black src/
isort src/
```

## 系统要求

- Python >= 3.10
- ffmpeg (系统级)
- CUDA >= 11.8 (可选，用于 GPU 加速)
