#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试优化后的DoubaoTTS WebSocket连接池
"""

from ttsreal import DoubaoTTS, State
from logger import logger
import numpy as np
import time
import threading
import os
import sys

sys.path.insert(0, '/Users/lukeding/Desktop/playground/2025/LiveTalking')


# 模拟配置
class MockOpt:
    def __init__(self):
        self.REF_FILE = "female"
        self.fps = 25
        self.TTS_SERVER = ""


class MockParent:
    def __init__(self):
        self.state = State.RUNNING
        self.audio_track = None
        self.loop = None
        self.audio_frames = []

    def put_audio_frame(self, chunk, eventpoint):
        self.audio_frames.append({
            'chunk': chunk,
            'eventpoint': eventpoint,
            'timestamp': time.time()
        })
        if len(self.audio_frames) % 10 == 0:
            logger.info(f"[TEST] 已接收 {len(self.audio_frames)} 个音频帧")


def test_connection_reuse():
    """测试连接复用"""
    print("\n" + "="*60)
    print("测试1: WebSocket连接复用")
    print("="*60)

    # 检查环境变量
    if not os.getenv("DOUBAO_APPID") or not os.getenv("DOUBAO_TOKEN"):
        print("❌ 请先设置环境变量:")
        print("  export DOUBAO_APPID='your_appid'")
        print("  export DOUBAO_TOKEN='your_token'")
        print("  export DOUBAO_VOICE_ID='female'")
        return False

    opt = MockOpt()
    parent = MockParent()

    # 创建TTS实例
    print("🚀 创建DoubaoTTS实例...")
    tts = DoubaoTTS(opt, parent)

    # 检查连接池
    print(f"✅ 连接池状态: {tts.get_stats()}")

    # 模拟多次请求
    test_texts = [
        "你好，这是第一个测试句子。",
        "这是第二个测试句子，看看连接是否复用。",
        "第三个句子，继续测试连接池功能。",
        "第四个句子，验证性能提升。",
        "第五个句子，完成基础测试。"
    ]

    print(f"\n📝 开始发送 {len(test_texts)} 个测试请求...")

    start_time = time.time()
    total_reuses_start = tts.connection_pool.total_reuses

    for i, text in enumerate(test_texts, 1):
        print(f"\n[{i}/{len(test_texts)}] 发送: {text[:20]}...")

        # 清空之前的音频帧
        parent.audio_frames.clear()

        # 发送请求
        tts.txt_to_audio((text, {'text': text}))

        # 显示当前连接状态
        stats = tts.get_stats()
        print(f"    连接数: {stats['connection_pool']['total_connections']}, "
              f"复用次数: {stats['connection_pool']['total_reuses']}, "
              f"音频帧: {len(parent.audio_frames)}")

        # 短暂延迟，模拟真实场景
        time.sleep(0.5)

    end_time = time.time()
    total_reuses_end = tts.connection_pool.total_reuses

    print(f"\n📊 测试结果:")
    print(f"  总耗时: {end_time - start_time:.2f}s")
    print(f"  复用次数: {total_reuses_end - total_reuses_start}")
    print(f"  平均每请求: {(end_time - start_time) / len(test_texts):.2f}s")

    # 最终状态
    final_stats = tts.get_stats()
    print(f"\n🔧 最终连接池状态:")
    print(f"  活跃连接: {final_stats['connection_pool']['total_connections']}")
    print(f"  可用连接: {final_stats['connection_pool']['available_connections']}")
    print(f"  总复用: {final_stats['connection_pool']['total_reuses']}")

    # 验证连接复用
    if total_reuses_end > total_reuses_start:
        print("\n✅ 连接复用成功！")
        return True
    else:
        print("\n❌ 连接复用失败！")
        return False


def test_concurrent_requests():
    """测试并发请求"""
    print("\n" + "="*60)
    print("测试2: 并发请求处理")
    print("="*60)

    if not os.getenv("DOUBAO_APPID"):
        print("❌ 跳过测试（缺少环境变量）")
        return False

    opt = MockOpt()
    parent = MockParent()

    print("🚀 创建DoubaoTTS实例...")
    tts = DoubaoTTS(opt, parent)

    results = []

    def worker(text, worker_id):
        """工作线程"""
        try:
            start = time.time()
            parent.audio_frames.clear()
            tts.txt_to_audio((text, {'text': text}))
            duration = time.time() - start
            results.append({
                'worker_id': worker_id,
                'duration': duration,
                'frames': len(parent.audio_frames)
            })
            print(
                f"  Worker {worker_id}: {duration:.2f}s, {len(parent.audio_frames)} frames")
        except Exception as e:
            print(f"  Worker {worker_id}: 错误 - {e}")

    # 创建并发请求
    threads = []
    test_texts = [
        "并发测试句子1",
        "并发测试句子2",
        "并发测试句子3"
    ]

    print(f"\n📝 启动 {len(test_texts)} 个并发线程...")

    for i, text in enumerate(test_texts):
        t = threading.Thread(target=worker, args=(text, i+1))
        threads.append(t)
        t.start()

    # 等待所有线程完成
    for t in threads:
        t.join()

    print(f"\n📊 并发测试结果:")
    print(f"  完成请求数: {len(results)}")
    if results:
        avg_time = sum(r['duration'] for r in results) / len(results)
        print(f"  平均耗时: {avg_time:.2f}s")
        print(f"  总音频帧: {sum(r['frames'] for r in results)}")

    # 检查连接池状态
    stats = tts.get_stats()
    print(f"\n🔧 连接池状态:")
    print(f"  活跃连接: {stats['connection_pool']['total_connections']}")
    print(f"  最大连接: {stats['connection_pool']['max_connections']}")

    if len(results) == len(test_texts):
        print("\n✅ 并发测试通过！")
        return True
    else:
        print("\n❌ 并发测试失败！")
        return False


def test_connection_health():
    """测试连接健康检查"""
    print("\n" + "="*60)
    print("测试3: 连接健康检查")
    print("="*60)

    if not os.getenv("DOUBAO_APPID"):
        print("❌ 跳过测试（缺少环境变量）")
        return False

    opt = MockOpt()
    parent = MockParent()

    print("🚀 创建DoubaoTTS实例...")
    tts = DoubaoTTS(opt, parent)

    # 获取一个连接
    print("\n📡 获取连接...")
    conn = tts.connection_pool.get_connection()

    if conn:
        print(f"✅ 连接成功")
        print(f"   - 状态: {'健康' if conn.is_healthy() else '不健康'}")
        print(f"   - 错误次数: {conn.error_count}")
        print(f"   - 最后使用: {time.time() - conn.last_used:.2f}s 前")

        # 归还连接
        print("\n🔄 归还连接...")
        tts.connection_pool.return_connection(conn)

        # 再次获取（应该复用）
        print("\n🔄 再次获取连接（应该复用）...")
        conn2 = tts.connection_pool.get_connection()

        if conn2 and conn2 == conn:
            print("✅ 连接成功复用！")
            result = True
        else:
            print("❌ 连接未复用！")
            result = False

        # 归还
        if conn2:
            tts.connection_pool.return_connection(conn2)
    else:
        print("❌ 无法获取连接")
        result = False

    # 显示统计
    stats = tts.get_stats()
    print(f"\n🔧 最终统计:")
    print(f"  {stats}")

    return result


def main():
    """主测试流程"""
    print("\n" + "="*80)
    print("DoubaoTTS WebSocket 连接池优化测试")
    print("="*80)

    # 检查环境
    print("\n📋 环境检查:")
    required_vars = ["DOUBAO_APPID", "DOUBAO_TOKEN", "DOUBAO_VOICE_ID"]
    for var in required_vars:
        value = os.getenv(var)
        status = "✅" if value else "❌"
        print(f"  {status} {var}: {'***' if value else '未设置'}")

    if not all(os.getenv(v) for v in required_vars):
        print("\n⚠️  请设置所有必需的环境变量后重试")
        return

    # 运行测试
    results = []

    try:
        results.append(("连接复用测试", test_connection_reuse()))
        time.sleep(1)

        results.append(("并发请求测试", test_concurrent_requests()))
        time.sleep(1)

        results.append(("连接健康检查", test_connection_health()))
    except Exception as e:
        print(f"\n❌ 测试执行异常: {e}")
        import traceback
        traceback.print_exc()

    # 总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print(f"\n📊 总体结果: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！优化版本工作正常！")
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查问题")


if __name__ == "__main__":
    main()
