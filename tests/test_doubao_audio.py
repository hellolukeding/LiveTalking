#!/usr/bin/env python3
"""
测试豆包TTS音频数据质量
"""
import os
import sys
import wave
import numpy as np

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

def test_doubao_tts():
    """测试豆包TTS并保存原始音频"""
    import uuid
    import time
    
    # 导入连接管理器
    from ttsreal import DoubaoWebSocketManager
    
    appid = os.getenv("DOUBAO_APPID")
    access_key = os.getenv("DOUBAO_ACCESS_TOKEN") or os.getenv("DOUBAO_AccessKeyID")
    voice_id = os.getenv("DOUBAO_VOICE_ID")
    resource_id = os.getenv("DOUBAO_RESOURCE_ID")
    
    print(f"APPID: {appid}")
    print(f"Voice ID: {voice_id}")
    print(f"Resource ID: {resource_id}")
    
    if not all([appid, access_key, voice_id]):
        print("缺少环境变量配置")
        return
    
    # 创建连接
    conn = DoubaoWebSocketManager(appid, access_key, voice_id, resource_id)
    if not conn.connect():
        print("连接失败")
        return
    
    # 发送请求
    text = "你好，这是一个测试。"
    reqid = str(uuid.uuid4())
    
    if not conn.send_text_request(text, reqid, context_texts=[]):
        print("发送请求失败")
        return
    
    # 收集音频数据
    all_audio_bytes = b''
    chunk_count = 0
    
    while True:
        result = conn.receive_audio_chunk(timeout=30.0)
        if result is None:
            break
        if isinstance(result, bytes) and len(result) > 0:
            chunk_count += 1
            all_audio_bytes += result
            print(f"收到chunk {chunk_count}: {len(result)} bytes")
    
    conn.close()
    
    if not all_audio_bytes:
        print("未收到音频数据")
        return
    
    print(f"\n总共收到 {len(all_audio_bytes)} bytes, {chunk_count} chunks")
    
    # 确保字节对齐
    aligned_len = (len(all_audio_bytes) // 2) * 2
    all_audio_bytes = all_audio_bytes[:aligned_len]
    
    # 转换为numpy数组
    audio_int16 = np.frombuffer(all_audio_bytes, dtype=np.int16)
    audio_float = audio_int16.astype(np.float32) / 32767.0
    
    print(f"\n=== 音频数据分析 ===")
    print(f"样本数: {len(audio_int16)}")
    print(f"时长: {len(audio_int16) / 16000:.2f} 秒")
    print(f"Int16 范围: [{audio_int16.min()}, {audio_int16.max()}]")
    print(f"Float32 范围: [{audio_float.min():.4f}, {audio_float.max():.4f}]")
    print(f"均值: {audio_float.mean():.6f}")
    print(f"标准差: {audio_float.std():.4f}")
    
    # 检查异常值
    clipped = np.sum(np.abs(audio_float) > 0.99)
    if clipped > 0:
        print(f"⚠️ 接近饱和的样本: {clipped}")
    
    # 检查大跳变
    diff = np.abs(np.diff(audio_float))
    large_jumps = np.sum(diff > 0.3)
    if large_jumps > 0:
        print(f"⚠️ 大跳变 (>0.3): {large_jumps}")
        # 找出跳变位置
        jump_indices = np.where(diff > 0.3)[0]
        print(f"   跳变位置: {jump_indices[:10]}...")
    
    # 保存原始音频
    output_file = "doubao_raw_audio.wav"
    with wave.open(output_file, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(audio_int16.tobytes())
    
    print(f"\n✅ 已保存原始音频: {output_file}")
    print("请用音频播放器检查是否有噪声")

if __name__ == '__main__':
    test_doubao_tts()
