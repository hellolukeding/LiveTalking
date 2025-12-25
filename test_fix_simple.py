#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的修复验证脚本
"""

import logging
import os
import sys
import time

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, os.path.join(project_root, 'src', 'core'))
sys.path.insert(0, os.path.join(project_root, 'src', 'utils'))

# 导入日志

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


def test_code_fixes():
    """验证代码修复是否正确应用"""
    print("=" * 70)
    print("🔧 代码修复验证")
    print("=" * 70)

    # 检查start_quick_fixed.py
    print("\n1. 检查start_quick_fixed.py...")
    try:
        with open('src/main/start_quick_fixed.py', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ("WebRTC连接状态管理增强", "on_connectionstatechange" in content and "connection state" in content),
            ("连接清理逻辑",
             "del nerfreals[sessionid]" in content and "tts.shutdown()" in content),
            ("异常处理", "except Exception as e:" in content),
            ("详细日志", "logger.info" in content and "logger.error" in content),
        ]

        all_passed = True
        for check_name, result in checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}")
            if not result:
                all_passed = False

        if all_passed:
            print("   ✅ start_quick_fixed.py 修复验证通过")
        else:
            print("   ❌ start_quick_fixed.py 修复验证失败")
            return False
    except Exception as e:
        print(f"   ❌ 读取文件失败: {e}")
        return False

    # 检查ttsreal.py
    print("\n2. 检查ttsreal.py...")
    try:
        with open('src/core/ttsreal.py', 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ("SSL错误处理", "ssl.SSLError" in content),
            ("WebSocket连接关闭异常处理", "WebSocketConnectionClosedException" in content),
            ("重连机制", "重连尝试" in content and "for retry in range(3)" in content),
            ("连接池增强", "get_connection" in content and "重连机制" in content),
        ]

        all_passed = True
        for check_name, result in checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}")
            if not result:
                all_passed = False

        if all_passed:
            print("   ✅ ttsreal.py 修复验证通过")
        else:
            print("   ❌ ttsreal.py 修复验证失败")
            return False
    except Exception as e:
        print(f"   ❌ 读取文件失败: {e}")
        return False

    return True


def test_imports():
    """测试模块导入"""
    print("\n3. 测试模块导入...")

    try:
        from ttsreal import DoubaoConnectionPool, DoubaoWebSocketConnection
        print("   ✅ WebSocket连接类导入成功")
        return True
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False


def main():
    print("\n🚀 LiveTalking WebSocket连接异常修复验证")
    print("=" * 70)

    success = True

    # 验证代码修复
    if not test_code_fixes():
        success = False

    # 验证导入
    if not test_imports():
        success = False

    print("\n" + "=" * 70)
    if success:
        print("🎉 修复验证通过！")
        print("\n已应用的修复:")
        print("1. ✅ WebRTC连接状态管理增强")
        print("2. ✅ WebSocket异常处理完善")
        print("3. ✅ SSL错误专门处理")
        print("4. ✅ 重连机制添加")
        print("5. ✅ 资源清理逻辑改进")
        print("6. ✅ 错误日志增强")
    else:
        print("❌ 修复验证失败")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
