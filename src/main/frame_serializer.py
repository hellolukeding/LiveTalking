# src/main/frame_serializer.py
"""音视频帧序列化工具 - 用于跨进程传输"""
import logging
from av import AudioFrame, VideoFrame
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def serialize_audio_frame(frame: AudioFrame) -> Dict[str, Any]:
    """将 AudioFrame 序列化为可跨进程传输的字典"""
    return {
        'format': frame.format.name,
        'layout': frame.layout.name,
        'samples': frame.samples,
        'planes': [plane.to_bytes() for plane in frame.planes]
    }

def serialize_video_frame(frame: VideoFrame) -> Dict[str, Any]:
    """将 VideoFrame 序列化为可跨进程传输的字典"""
    return {
        'format': frame.format.name,
        'width': frame.width,
        'height': frame.height,
        'data': frame.to_bytes()
    }

def deserialize_audio_frame(data: Dict[str, Any]) -> AudioFrame:
    """从字典重建 AudioFrame"""
    frame = AudioFrame(
        format=data['format'],
        layout=data['layout'],
        samples=data['samples']
    )
    for i, plane_bytes in enumerate(data['planes']):
        frame.planes[i].update(plane_bytes)
    return frame

def deserialize_video_frame(data: Dict[str, Any]) -> VideoFrame:
    """从字典重建 VideoFrame"""
    frame = VideoFrame(
        width=data['width'],
        height=data['height']
    )
    if 'data' in data:
        frame.update(data['data'])
    return frame
