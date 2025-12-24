#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证音频修复 - 检查关键代码是否正确修改
"""

import sys
import re


def check_file_content(filepath, checks):
    """检查文件内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        results = []
        for check_name, pattern, should_exist in checks:
            found = bool(re.search(pattern, content, re.MULTILINE | re.DOTALL))
            passed = found == should_exist
            results.append((check_name, passed, found, should_exist))
        
        return results
    except Exception as e:
        print(f"❌ 读取文件失败 {filepath}: {e}")
        return None


def main():
    print("=" * 70)
    print("验证 DoubaoTTS 音频修复")
    print("=" * 70)
    
    all_passed = True
    
    # 检查 ttsreal.py
    print("\n[1] 检查 ttsreal.py...")
    tts_checks = [
        ("移除direct_to_webrtc判断", 
         r"if getattr\(self, 'direct_to_webrtc'.*?\):", 
         False),
        ("统一调用parent.put_audio_frame", 
         r"self\.parent\.put_audio_frame\(chunk, eventpoint\)", 
         True),
        ("结束事件调用parent", 
         r"def _send_end_event.*?self\.parent\.put_audio_frame", 
         True),
    ]
    
    tts_results = check_file_content("ttsreal.py", tts_checks)
    if tts_results:
        for name, passed, found, should_exist in tts_results:
            status = "✅" if passed else "❌"
            expect = "应存在" if should_exist else "不应存在"
            actual = "存在" if found else "不存在"
            print(f"  {status} {name}: {expect}, 实际{actual}")
            if not passed:
                all_passed = False
    
    # 检查 basereal.py
    print("\n[2] 检查 basereal.py...")
    base_checks = [
        ("先转发到LipASR", 
         r"# 🆕 修复：先转发给ASR.*?self\.lip_asr\.put_audio_frame", 
         True),
        ("音频块填充逻辑", 
         r"if len\(frame\) < chunk_size:.*?padded = np\.zeros", 
         True),
        ("提高队列容量阈值", 
         r"if queue_size > 100:", 
         True),
        ("添加转发日志", 
         r"Audio forwarded to LipASR", 
         True),
    ]
    
    base_results = check_file_content("basereal.py", base_checks)
    if base_results:
        for name, passed, found, should_exist in base_results:
            status = "✅" if passed else "❌"
            expect = "应存在" if should_exist else "不应存在"
            actual = "存在" if found else "不存在"
            print(f"  {status} {name}: {expect}, 实际{actual}")
            if not passed:
                all_passed = False
    
    # 总结
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ 所有检查通过！音频修复已正确应用。")
        print("\n下一步:")
        print("1. 重启应用程序")
        print("2. 测试TTS播放，检查是否有声音")
        print("3. 观察数字人口型是否正常驱动")
        print("4. 查看日志确认音频转发: grep 'Audio forwarded' livetalking.log")
    else:
        print("❌ 部分检查未通过，请检查修复是否完整。")
        print("\n建议:")
        print("1. 重新应用修复")
        print("2. 检查文件是否被正确修改")
        print("3. 查看 AUDIO_FIX_SUMMARY.md 了解详细修复方案")
    print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
