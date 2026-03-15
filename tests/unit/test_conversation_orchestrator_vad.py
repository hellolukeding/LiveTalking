import asyncio
import os
import sys

import numpy as np

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "src", "core"))
sys.path.insert(0, os.path.join(project_root, "src", "main"))

import conversation_orchestrator as orch_mod  # noqa: E402


class _DummyNerfreal:
    def __init__(self, speaking: bool = False):
        self._speaking = speaking
        self.interrupt_count = 0

    def is_speaking(self) -> bool:
        return self._speaking

    def flush_talk(self):
        self.interrupt_count += 1

    def put_msg_txt(self, msg: str, datainfo: dict = None):
        # Not needed for these tests.
        pass


class _FakeTime:
    def __init__(self, t0: float = 100.0):
        self.t = t0

    def perf_counter(self) -> float:
        return self.t

    def advance(self, dt: float):
        self.t += dt


def _audio_with_rms(rms: float, n: int = 320) -> np.ndarray:
    # Constant signal has exact RMS == abs(value).
    return np.full((n,), float(rms), dtype=np.float32)


def test_vad_more_sensitive_triggers_turn(monkeypatch):
    async def _run():
        fake_time = _FakeTime()
        monkeypatch.setattr(orch_mod.time, "perf_counter", fake_time.perf_counter)

        nerfreal = _DummyNerfreal(speaking=False)
        opt = type("Opt", (), {})()
        orch = orch_mod.ConversationOrchestrator(1, nerfreal, opt)
        orch.cfg.cooldown_ms = 0  # deterministic

        scheduled = {"count": 0}

        async def _fake_run_turn(turn_id: int, audio: np.ndarray, sr_in: int):
            scheduled["count"] += 1

        monkeypatch.setattr(orch, "_run_turn", _fake_run_turn)

        # 500ms of low-volume speech (RMS 0.007) should trigger with default threshold 0.006.
        for _ in range(25):  # 25 * 20ms = 500ms
            orch.ingest_audio(_audio_with_rms(0.007), 16000)
            fake_time.advance(0.02)

        # 500ms silence to endpoint (end_silence_ms default 400ms).
        for _ in range(25):
            orch.ingest_audio(_audio_with_rms(0.0), 16000)
            fake_time.advance(0.02)

        await asyncio.sleep(0)  # let create_task run
        assert scheduled["count"] == 1

    asyncio.run(_run())


def test_barge_in_interrupts_tts(monkeypatch):
    fake_time = _FakeTime()
    monkeypatch.setattr(orch_mod.time, "perf_counter", fake_time.perf_counter)

    nerfreal = _DummyNerfreal(speaking=True)
    opt = type("Opt", (), {})()
    orch = orch_mod.ConversationOrchestrator(2, nerfreal, opt)
    orch.cfg.cooldown_ms = 0

    # Feed >200ms of barge-in audio above threshold.
    for _ in range(12):  # 12 * 20ms = 240ms
        orch.ingest_audio(_audio_with_rms(0.02), 16000)
        fake_time.advance(0.02)

    assert nerfreal.interrupt_count == 1
    assert orch._in_speech is True
