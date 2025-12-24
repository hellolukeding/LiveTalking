#!/usr/bin/env python3
"""
调试音频格式和内容
"""

import numpy as np
import base64
import requests
import json
import os
from logger import logger


def test_doubao_audio_format():
    """测试豆包TTS返回的音频格式"""

    # 模拟豆包TTS请求
    appid = os.getenv("DOUBAO_APPID")
    token = os.getenv("DOUBAO_TOKEN")
    voice_id = os.getenv(
        "DOUBAO_VOICE_ID") or "zh_female_shuangkuaisisi_moon_bigtts"

    if not appid or not token:
        print("❌ 缺少环境变量")
        return

    api_url = "https://openspeech.bytedance.com/api/v1/tts"

    request_json = {
        "app": {
            "appid": appid,
            "token": token,
            "cluster": "volcano_tts"
        },
        "user": {
            "uid": "test-user-123"
        },
        "audio": {
            "voice_type": voice_id,
            "encoding": "wav",
            "rate": 16000,
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": "test-req-123",
            "text": "测试音频            "text_type": "plain",
            "operation": "query"
        }
    }
    
    print("🔍 发送TTS请求...")
    try:
        response = requests.post(
            api_url,
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ HTTP错误: {response.status_code}")
            return
        
        result = response.json()
        
        if result.get("code", 0) != 3000:
            print(f"❌ API错误: {result.get('code')}, {result.get('message')}")
            return
        
        # 获取音频数据
        audio_base64 = None
        if "data" in result:
            if isinstance(result["data"], dict):
                audio_base64 = result["data"].get("audio              )
。
。
。
。。
        audio audio音频 audio音频 audio audio audio audio audio audio audio audio base base. audio audio audio6audio(base base6 audio audio base6 base6 print audio audio        print print print print6

6 print print base
 print audio print base print print audio        print audio audio        = print print print print print print        = audio audio print audio        print print print print6 = audio audio        print audio        print type audio print print        print
 print        print base print)
 print

 print print
音频        print print audio
 print print print print print)

        print print(f❌❌❌ Base6音频 audio_base6
        return
    
        # 解码base6 audio_bytes = base base6 base       .decode.b64        print(f❌❌ Base64解码失败: {e}")
        return
    
       try_bytes6 print        print(f"✅ Base音频数据: {len(audio64 bytes)} bytes}")
 bytes")
               print(f"🔍 音音频音频数据长度6 bytes bytes)")
        
")
        

        
 # # 转音频 dtypearray = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_array.astype(np.float32) / 32767.0
        
        print(f"📊 音频数据分析:")
        print(f"   - 原始字节: {len(audio_bytes)} bytes")
        print(f"   - 16-bit数组: {audio_array.shape} - 范围: [{audio_array.min()}, {audio_array.max()}]")
        print(f"   - 32-bit数组: {audio_float.shape} - 范围: [{audio_float.min():.4f}, {audio_float.max():.4f}]")
        print(f"   - 音频   -  print = - print - = -  - print = print print = =  = = =  = = - = = =  - print = =  =  =  =
 =    = =
 print
 print
 print print print
 =
 print         = -

        

 : print  - -       
 =  - -   - = =
 =:
 print -        

 -print   
)
: = =
  {

 =       


  不仅不仅 print print 
 =不仅 不仅2  - /               3. 3  3  3 - 3
        =  = 0
  print(f"❌ 无法获取音频频")
        return
    
    print(f"🔍  音分析...")
        print(f"32767.0, 32767.0, 32767.0)
        print(f"   - 最小值: {audio_float.min():.4f}, { audio_max():.4f}]")
        
        print(f"   - - 32-bit数组: {audio_float.min():..f}, max={audio_float.max():.4f}]")
        
        # 检查是否包含异常值
        if np.any(np.isnan(audio_float)) or np.any(np.isinf(audio_float)):
            print("❌ 音频包含NaN或Inf值！")
        
        # 检查是否大部分是静音
        silent_ratio = np.sum(np.abs(audio_float) < 0.01) / len(audio_float)
        print(f"   - 静音比例: {silent_ratio:.2%}")
        
        # 检查音频长度
        duration_ms = len(audio_float) / 16000 * 1000
        print(f"   - 音频时长: {duration_ms:.1f}ms")
        
        # 检查320样本块
        chunk_size = 320
        if len(audio_float) >= chunk_size:
            first_chunk = audio_float[:chunk_size]
            print(f"   - 第一个320样本块: 范围 [{first_chunk.min():.4f}, {first_chunk.max():.4f}]")
            print(f"   - 第一个320样本块的静音比例: {np.sum(np.abs(first_chunk) < 0.01) / chunk_size:.2%}")
        
        return audio_float
        
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_audio_conversion():
    """测试音频格式转换"""
    print("\n" + "="*60)
    print("测试音频格式转换")
    print("="*60)
    
    # 生成测试音频
    test_audio = np.random.randn(320).astype(np.float32) * 0.1
    
    print(f"原始音频: {test_audio.dtype}, 范围: [{test_audio.min():.4f {test_audio.max():.4f}]")
    
    # 转换为16-bit
    frame = (test_audio * 32767).astype(np.int16)
    print(f"16-bit音频: {frame.dtype}, 范围: [{frame.min()}, {frame.max()}]")
    
    # 创建AudioFrame
    frame_2d = frame.reshape(1, -1)
    from av import AudioFrame
    new_frame = AudioFrame.from_ndarray(frame_2d, layout='mono', format='s16')
    new_frame.sample_rate = 16000
    
    print(f"AudioFrame: format={new_frame.format}, layout={new_frame.layout}")
    print(f"AudioFrame: sample_rate={new_frame.sample_rate}, samples={new_frame.samples}")
    
    # 模拟WebRTC接收
    if hasattr(new_frame, 'to_ndarray'):
        received = new_frame.to_ndarray()
        print(f"接收音频: {received.dtype}, 范围: [{received.min()}, {received.max()}]")
        
        # 转换回float
        received_float = received.astype(np.float32) / 32767.0
        print(f"接收音频(float): {received_float.dtype}, 范围: [{received_float.min():.4f}, {received_float.max():.4f}]")
        
        # 检查失真
        diff = np.abs(test_audio - received_float)
        print(f"失真: 最大={diff.max():.6f}, 平均={diff.mean():.6f}")

if __name__ == "__main__":
    print("🔍 LiveTalking 音频调试工具")
    print("="*60)
    
    # 测试豆包TTS
    audio = test_doubao_audio_format()
    
    if audio is not None:
        # 测试格式转换
        test_audio_conversion()
        
        print("\n" + "="*60)
        print("调试完成")
        print("="*60)
