import os
import sys

import numpy as np
from av import AudioFrame, VideoFrame


def test_audio_frame_roundtrip():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, "src", "main"))

    from frame_serializer import serialize_audio_frame, deserialize_audio_frame

    samples = (np.arange(320) % 100).astype(np.int16)
    frame = AudioFrame(format="s16", layout="mono", samples=samples.shape[0])
    frame.planes[0].update(samples.tobytes())
    frame.sample_rate = 16000

    data = serialize_audio_frame(frame)
    restored = deserialize_audio_frame(data)

    assert restored.format.name == "s16"
    assert restored.layout.name == "mono"
    assert restored.samples == 320
    assert restored.sample_rate == 16000
    assert bytes(restored.planes[0]) == samples.tobytes()


def test_video_frame_roundtrip_bgr24():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, "src", "main"))

    from frame_serializer import serialize_video_frame, deserialize_video_frame

    img = np.zeros((32, 32, 3), dtype=np.uint8)
    img[:, :, 2] = 255
    frame = VideoFrame.from_ndarray(img, format="bgr24")

    data = serialize_video_frame(frame)
    restored = deserialize_video_frame(data)

    restored_img = restored.to_ndarray(format="bgr24")
    assert restored.width == 32
    assert restored.height == 32
    assert restored_img.shape == img.shape
    assert int(restored_img.sum()) == int(img.sum())
