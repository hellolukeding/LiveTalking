import asyncio
import os
import queue
import sys

import numpy as np
from av import AudioFrame


def test_eventpoint_payload_forwarded_to_notifier():
    import pytest
    pytest.importorskip("aiortc")

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, "src", "main"))

    from frame_serializer import serialize_audio_frame
    from queue_track import AVSyncClock, QueueAudioTrack

    samples = np.zeros((320,), dtype=np.int16)
    frame = AudioFrame(format="s16", layout="mono", samples=samples.shape[0])
    frame.planes[0].update(samples.tobytes())
    frame.sample_rate = 16000

    q = queue.Queue()
    q.put({
        "frame": serialize_audio_frame(frame),
        "eventpoint": {"status": "end", "text": "test"},
    })

    received = []
    track = QueueAudioTrack(
        q,
        session_id="eventpoint-test",
        clock=AVSyncClock(required_kinds={"audio"}),
        event_notifier=lambda ep: received.append(ep),
    )

    async def _recv_once():
        out = await track.recv()
        assert out.samples == 320
        assert out.sample_rate == 16000

    asyncio.run(_recv_once())
    assert received == [{"status": "end", "text": "test"}]
