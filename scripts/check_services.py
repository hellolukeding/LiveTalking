#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务健康检查脚本
用于手动检查ASR和TTS服务的可用性
"""

from service_health_check import ServiceHealthChecker
import os
import sys

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """主函数"""
    print("=" * 70)
    print("🤖 LiveTalking 服务健康检查工具")
    print("=" * 70)
    print()

    checker = ServiceHealthChecker()
    success = checker.check_all()

    print()
    print("=" * 70)
    if success:
        print("✅ 所有服务健康检查通过")
        print("🎉 可以正常启动 LiveTalking 项目")
        print()
        print("启动命令:")
        print("  python app.py")
    else:
        print("❌ 部分服务检查失败")
        print()
        print("请检查以下内容:")
        print("1. 确保 .env 文件配置正确")
        print("2. 检查网络连接")
        print("3. 确认TTS/ASR服务已启动")
        print("4. 检查API密钥是否有效")
        print()
        print("配置文件位置: .env")
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
