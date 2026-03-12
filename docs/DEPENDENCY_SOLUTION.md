# LiveTalking 依赖管理解决方案

## 问题背景

在运行 LiveTalking 项目时，经常遇到 `ModuleNotFoundError` 错误，原因包括：

1. **依赖不完整** - requirements.txt 缺少部分运行时依赖
2. **隐式依赖** - 某些包被其他包间接依赖，但未显式声明
3. **SOCKS 代理** - OpenAI SDK 在使用代理时需要 socksio

## 解决方案

### 1. 创建的文件

```
LiveTalking/
├── requirements_full.txt          # 完整依赖列表
├── scripts/
│   ├── install_deps.sh            # 一键安装脚本
│   ├── check_deps.py              # 依赖检查工具
│   ├── fix_deps.sh                # 快速修复脚本
│   └── ensure_deps.py             # 启动前最小依赖检查
└── docs/
    ├── DEPENDENCIES.md            # 依赖管理文档
    └── DEPENDENCY_SOLUTION.md     # 本文档
```

### 2. 关键新增依赖

| 包名 | 用途 | 之前缺失 |
|------|------|---------|
| `pydub` | WebM 转 WAV | ✗ |
| `socksio` | SOCKS 代理支持 | ✗ |
| `httpx` | HTTP 客户端 | ✗ |
| `websocket-client` | WebSocket 客户端 | ✗ |
| `torchvision` | 计算机视觉 | ✗ |
| `torchaudio` | 音频处理 | ✗ |
| `scikit-learn` | 机器学习 | ✗ |

### 3. 使用方法

#### 初次安装

```bash
# 克隆项目后
cd /opt/2026/LiveTalking

# 一键安装所有依赖
./scripts/install_deps.sh
```

#### 日常开发

```bash
# 启动服务前会自动检查依赖
python src/main/app.py --model wav2lip --tts doubao

# 或手动检查
python scripts/check_deps.py
```

#### 遇到依赖错误时

```bash
# 快速修复常见缺失依赖
./scripts/fix_deps.sh

# 或完整重新安装
pip install -r requirements_full.txt
```

### 4. CI/CD 集成

在 CI/CD 流程中添加依赖检查：

```yaml
# .github/workflows/test.yml
- name: Check dependencies
  run: python scripts/check_deps.py

- name: Install missing dependencies
  run: ./scripts/fix_deps.sh
```

### 5. Docker 支持

创建 Dockerfile 时使用完整依赖：

```dockerfile
COPY requirements_full.txt .
RUN pip install -r requirements_full.txt
```

## 技术细节

### 依赖检查原理

`check_deps.py` 通过尝试导入每个模块来验证依赖是否已安装：

```python
def check_module(module_name: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, ""
    except ImportError as e:
        return False, str(e)
```

### 启动前检查

`ensure_deps.py` 只检查运行时必需的最小依赖集，避免影响启动速度。

### 模块名映射

某些包的导入名称与 pip 名称不同：

| pip 名称 | 导入名称 |
|----------|---------|
| `opencv-python` | `cv2` |
| `scikit-learn` | `sklearn` |
| `Pillow` | `PIL` |
| `websocket-client` | `websocket` |

## 维护指南

### 添加新依赖

1. 在 `pyproject.toml` 中添加
2. 更新 `requirements_full.txt`
3. 在 `check_deps.py` 的 `CORE_DEPENDENCIES` 中添加检查项
4. 运行 `pip install <new_package>`

### 更新依赖版本

```bash
# 查看过时的包
pip list --outdated

# 更新特定包
pip install --upgrade <package_name>

# 更新 requirements_full.txt
pip-compile pyproject.toml -o requirements_full.txt
```

## 常见错误修复

### 错误 1: ModuleNotFoundError: No module named 'pydub'

```bash
pip install pydub
# 或运行
./scripts/fix_deps.sh
```

### 错误 2: ImportError: Using SOCKS proxy, but the 'socksio' package is not installed

```bash
pip install socksio
```

### 错误 3: Failed to convert WebM to WAV for Tencent ASR: No module named 'pydub'

```bash
pip install pydub ffmpeg-python
# 确保系统已安装 ffmpeg
sudo apt-get install ffmpeg  # Ubuntu/Debian
```

### 错误 4: No module named 'av'

```bash
pip install av
```

## 验证

运行完整检查验证所有依赖：

```bash
python scripts/check_deps.py
```

期望输出：
```
============================================================
 LiveTalking 依赖检查
============================================================

Python 版本: 3.12.x
Python 路径: /path/to/python

============================================================
 核心依赖检查
============================================================
  ✓ PyTorch
  ✓ TorchVision
  ✓ TorchAudio
  ✓ AV (PyAV)
  ✓ AIORTC (WebRTC)
  ...

============================================================
 检查结果
============================================================

所有核心依赖已安装！
```

## 总结

通过以下措施彻底解决依赖缺失问题：

1. ✅ **完整的依赖声明** - requirements_full.txt 包含所有运行时依赖
2. ✅ **自动化检查** - 启动前自动检查依赖完整性
3. ✅ **快速修复** - 一键安装缺失依赖
4. ✅ **详细文档** - 完整的依赖管理指南
5. ✅ **CI/CD 友好** - 可集成到自动化流程

新环境部署只需运行：
```bash
./scripts/install_deps.sh
```

开发中遇到依赖问题时运行：
```bash
./scripts/fix_deps.sh
```
