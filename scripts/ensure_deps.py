#!/usr/bin/env python3
"""
启动前依赖检查
确保所有必需的依赖都已安装，如果缺失则提示安装
"""

import sys
import importlib

# 最小依赖集（服务运行必需）
MINIMAL_DEPENDENCIES = {
    'torch': 'PyTorch',
    'av': 'AV (PyAV)',
    'aiortc': 'AIORTC',
    'aiohttp': 'AIOHTTP',
    'httpx': 'HTTPX',
    'websocket': 'WebSockets',
    'pydub': 'Pydub',
    'socksio': 'socksio',
    'numpy': 'NumPy',
    'cv2': 'OpenCV',
    'soundfile': 'SoundFile',
    'resampy': 'Resampy',
    'transformers': 'Transformers',
    'edge_tts': 'Edge TTS',
    'openai': 'OpenAI',
    'flask': 'Flask',
    'flask_sockets': 'Flask-Sockets',
    'scipy': 'SciPy',
    'tqdm': 'TQDM',
    'omegaconf': 'OmegaConf',
}

def check_dependencies():
    """检查最小依赖集"""
    missing = []
    
    for module, display_name in MINIMAL_DEPENDENCIES.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(display_name)
    
    return missing

def main():
    missing = check_dependencies()
    
    if missing:
        print("❌ 缺失以下依赖:")
        for dep in missing:
            print(f"  - {dep}")
        print("\n请运行以下命令安装缺失的依赖:")
        print("  pip install -r requirements_full.txt")
        print("  或运行: ./scripts/fix_deps.sh")
        sys.exit(1)
    else:
        print("✓ 所有依赖已安装")
        sys.exit(0)

if __name__ == "__main__":
    main()
