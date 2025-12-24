#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 poetry run livetalking 是否能正常工作
"""

import os
import sys

# 添加路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, os.path.join(project_root, 'src', 'core'))
sys.path.insert(0, os.path.join(project_root, 'src', 'llm'))
sys.path.insert(0, os.path.join(project_root, 'src', 'utils'))
sys.path.insert(0, os.path.join(project_root, 'src', 'main'))

print("🧪 测试 poetry run livetalking")
print("=" * 50)

# 测试导入
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ dotenv 导入成功")
except ImportError as e:
    print(f"❌ dotenv 导入失败: {e}")

try:
    from logger import logger
    print("✅ logger 导入成功")
except ImportError as e:
    print(f"❌ logger 导入失败: {e}")

try:
    from start_quick_fixed import main
    print("✅ start_quick_fixed.main 导入成功")
    print("\n🎉 所有导入测试通过！")
    print("\n现在可以使用以下命令启动:")
    print("  poetry run livetalking")
    print("  或者")
    print("  python run_livetalking.py")
except ImportError as e:
    print(f"❌ start_quick_fixed.main 导入失败: {e}")
    print("\n请检查:")
    print("1. 是否在项目根目录")
    print("2. 是否已安装依赖: poetry install")
    print("3. 是否已激活虚拟环境: poetry shell")
