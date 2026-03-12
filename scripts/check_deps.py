#!/usr/bin/env python3
"""
LiveTalking 依赖检查工具
快速验证所有必需的依赖是否已正确安装
"""

import sys
import importlib
from typing import List, Tuple

# ANSI 颜色代码
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

# 核心依赖列表（模块名: 显示名称）
CORE_DEPENDENCIES = {
    'torch': 'PyTorch',
    'torchvision': 'TorchVision',
    'torchaudio': 'TorchAudio',
    'av': 'AV (PyAV)',
    'aiortc': 'AIORTC (WebRTC)',
    'aiohttp': 'AIOHTTP',
    'httpx': 'HTTPX',
    'websocket': 'WebSockets',
    'websocket': 'websocket-client',
    'pydub': 'Pydub',
    'socksio': 'socksio (SOCKS 代理)',
    'numpy': 'NumPy',
    'cv2': 'OpenCV',
    'PIL': 'Pillow',
    'soundfile': 'SoundFile',
    'librosa': 'Librosa',
    'resampy': 'Resampy',
    'transformers': 'Transformers',
    'edge_tts': 'Edge TTS',
    'openai': 'OpenAI',
    'flask': 'Flask',
    'flask_sockets': 'Flask-Sockets',
    'gradio_client': 'Gradio Client',
    'azure.cognitiveservices.speech': 'Azure Speech SDK',
    'scipy': 'SciPy',
    'sklearn': 'Scikit-learn',
    'tqdm': 'TQDM',
    'omegaconf': 'OmegaConf',
    'diffusers': 'Diffusers',
    'accelerate': 'Accelerate',
    'safetensors': 'SafeTensors',
}

# 可选依赖
OPTIONAL_DEPENDENCIES = {
    'sounddevice': 'SoundDevice (音频设备)',
    'pyaudio': 'PyAudio',
    'dearpygui': 'DearPyGui',
}

def check_module(module_name: str) -> Tuple[bool, str]:
    """检查单个模块是否可导入"""
    try:
        importlib.import_module(module_name)
        return True, ""
    except ImportError as e:
        return False, str(e)
    except Exception as e:
        return False, f"加载错误: {e}"

def print_header(text: str):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.GREEN}")
    print(f" {text}")
    print(f"{Colors.BLUE}{'='*60}{Colors.GREEN}")

def check_dependencies():
    """检查所有依赖"""
    print_header("LiveTalking 依赖检查")
    
    print(f"\nPython 版本: {Colors.YELLOW}{sys.version}{Colors.NC}")
    print(f"Python 路径: {Colors.YELLOW}{sys.executable}{Colors.NC}")
    
    # 检查核心依赖
    print_header("核心依赖检查")
    
    missing = []
    failed = []
    
    for module, display_name in CORE_DEPENDENCIES.items():
        success, error = check_module(module)
        if success:
            print(f"  {Colors.GREEN}✓{Colors.NC} {display_name}")
        else:
            print(f"  {Colors.RED}✗{Colors.NC} {display_name} {Colors.RED}({error}){Colors.NC}")
            missing.append((display_name, module))
    
    # 检查可选依赖
    print_header("可选依赖检查")
    
    for module, display_name in OPTIONAL_DEPENDENCIES.items():
        success, error = check_module(module)
        if success:
            print(f"  {Colors.GREEN}✓{Colors.NC} {display_name}")
        else:
            print(f"  {Colors.YELLOW}○{Colors.NC} {display_name} {Colors.YELLOW}(未安装){Colors.NC}")
    
    # 检查 ffmpeg
    print_header("外部工具检查")
    
    import shutil
    for tool in ['ffmpeg', 'ffprobe']:
        if shutil.which(tool):
            print(f"  {Colors.GREEN}✓{Colors.NC} {tool}")
        else:
            print(f"  {Colors.YELLOW}⚠{Colors.NC} {tool} {Colors.YELLOW}(未找到，可能需要安装){Colors.NC}")
    
    # 总结
    print_header("检查结果")
    
    if missing:
        print(f"\n{Colors.RED}缺失 {len(missing)} 个核心依赖:{Colors.NC}")
        for display_name, module in missing:
            print(f"  - {display_name} (模块名: {module})")
        print(f"\n{Colors.YELLOW}请运行安装命令:{Colors.NC}")
        print(f"  {Colors.YELLOW}pip install -r requirements_full.txt{Colors.NC}")
        return False
    else:
        print(f"\n{Colors.GREEN}所有核心依赖已安装！{Colors.NC}")
        return True

if __name__ == "__main__":
    success = check_dependencies()
    sys.exit(0 if success else 1)
