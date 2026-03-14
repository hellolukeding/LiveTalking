# src/main/frame_serializer.py
"""音视频帧序列化工具 - 用于跨进程传输"""
import logging
from av import AudioFrame, VideoFrame
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def serialize_audio_frame(frame: AudioFrame) -> Dict[str, Any]:
    """将 AudioFrame 序列化为可跨进程传输的字典"""
    return {
        'format': frame.format.name,
        'layout': frame.layout.name,
        'samples': frame.samples,
        'sample_rate': getattr(frame, "sample_rate", None),
        # PyAV Plane supports buffer protocol; bytes(plane) is the safe way.
        'planes': [bytes(plane) for plane in frame.planes],
    }

def serialize_video_frame(frame: VideoFrame) -> Dict[str, Any]:
    """将 VideoFrame 序列化为可跨进程传输的字典"""
    return {
        'format': frame.format.name if frame.format else None,
        'width': frame.width,
        'height': frame.height,
        # Use plane bytes; VideoFrame has no .to_bytes() in PyAV.
        'planes': [bytes(plane) for plane in frame.planes],
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
    if data.get("sample_rate"):
        frame.sample_rate = data["sample_rate"]
    return frame

def deserialize_video_frame(data: Dict[str, Any]) -> VideoFrame:
    """从字典重建 VideoFrame"""
    fmt = data.get("format")
    if not fmt:
        raise ValueError("Missing video frame format")

    frame = VideoFrame(width=data['width'], height=data['height'], format=fmt)

    planes: Optional[List[bytes]] = data.get("planes")
    if planes is None and "data" in data:
        # Back-compat: packed single-plane payload
        planes = [data["data"]]

    if planes:
        for i, plane_bytes in enumerate(planes):
            frame.planes[i].update(plane_bytes)
    return frame
