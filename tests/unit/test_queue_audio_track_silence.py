import os
import sys
import queue

import numpy as np
from av import AudioFrame


def test_silence_matches_stream_hints():
    import pytest
    pytest.importorskip("aiortc")

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, "src", "main"))

    from queue_track import QueueAudioTrack, DEFAULT_AUDIO_SAMPLES, DEFAULT_AUDIO_SAMPLE_RATE

    q = queue.Queue()
    track = QueueAudioTrack(q, session_id="test")

    s0 = track._make_silence()
    assert s0.sample_rate == DEFAULT_AUDIO_SAMPLE_RATE
    assert s0.samples == DEFAULT_AUDIO_SAMPLES

    samples = np.zeros((533,), dtype=np.int16)
    f = AudioFrame(format="s16", layout="mono", samples=samples.shape[0])
    f.planes[0].update(samples.tobytes())
    f.sample_rate = 16000

    track._update_stream_hints(f)

    s1 = track._make_silence()
    assert s1.sample_rate == 16000
    assert s1.samples == 533
