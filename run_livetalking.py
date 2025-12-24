#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LiveTalking 项目启动器
自动设置Python路径并启动应用
"""

import os
import subprocess
import sys


def main():
    print("=" * 70)
    print("🚀 LiveTalking 启动器")
    print("=" * 70)
    print()

    # 获取项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))

    # 检查必要的目录
    required_dirs = [
        os.path.join(project_root, 'src'),
        os.path.join(project_root, 'src', 'core'),
        os.path.join(project_root, 'src', 'main'),
        os.path.join(project_root, 'models'),
        os.path.join(project_root, 'frontend', 'web')
    ]

    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            print(f"❌ 目录不存在: {dir_path}")
            return 1

    # 检查环境变量文件
    env_file = os.path.join(project_root, '.env')
    if not os.path.exists(env_file):
        print("⚠️  警告: .env 文件不存在")
        print("请复制 .env.example 为 .env 并配置相关参数")
        print()

    # 设置Python路径
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, 'src'))
    sys.path.insert(0, os.path.join(project_root, 'src', 'core'))
    sys.path.insert(0, os.path.join(project_root, 'src', 'llm'))
    sys.path.insert(0, os.path.join(project_root, 'src', 'utils'))
    sys.path.insert(0, os.path.join(project_root, 'src', 'main'))

    print("📋 项目信息:")
    print(f"  项目根目录: {project_root}")
    print(f"  Python路径: 已设置")
    print()

    # 显示可用的启动选项
    print("🎯 请选择启动模式:")
    print("  1. 快速启动 (推荐) - 跳过健康检查")
    print("  2. 标准启动 - 包含健康检查")
    print("  3. 仅启动Web服务")
    print("  4. 查看帮助")
    print()

    choice = input("请输入选项 (1-4): ").strip()

    if choice == '1':
        # 使用修复版的快速启动脚本
        print("\n🔄 启动快速模式...")
        try:
            # 直接导入并运行
            sys.path.append(os.path.join(project_root, 'src', 'main'))
            from start_quick_fixed import main as quick_main
            quick_main()
        except ImportError as e:
            print(f"❌ 导入错误: {e}")
            print("请确保所有依赖已安装: poetry install")
            return 1

    elif choice == '2':
        # 标准启动 - 需要修复原始脚本的导入
        print("\n🔄 启动标准模式...")
        print("⚠️  注意: 原始start_quick.py需要修复导入路径")
        print("建议使用选项1 (快速启动)")
        return 0

    elif choice == '3':
        # 仅启动Web服务（用于测试）
        print("\n🔄 仅启动Web服务...")
        print("此功能需要单独实现")
        return 0

    elif choice == '4':
        # 显示帮助
        print("\n📖 使用说明:")
        print("1. 首次使用前，请确保:")
        print("   - 已安装Python 3.10-3.12")
        print("   - 已安装Poetry")
        print("   - 已配置 .env 文件")
        print("   - 已下载模型文件到 models/ 目录")
        print()
        print("2. 安装依赖:")
        print("   poetry install")
        print()
        print("3. 启动项目:")
        print("   python run_livetalking.py")
        print()
        print("4. 访问前端:")
        print("   http://localhost:8011/dashboard.html")
        print()
        print("5. 环境变量配置:")
        print("   - TTS_TYPE: tts服务类型 (edge/doubao/tencent/azure)")
        print("   - ASR_TYPE: asr服务类型 (lip/tencent)")
        print("   - LISTEN_PORT: Web服务端口 (默认8011)")
        print()

    else:
        print("❌ 无效选项")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
