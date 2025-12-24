#!/usr/bin/env python3
"""Generate a synthetic TTS-like WAV and run it through BaseReal.put_audio_file()

This script:
- generates a 3s 16kHz sine wave (simulates TTS output)
- writes it to data/tts_test.wav
- imports BaseReal (with a minimal dummy opt) and calls put_audio_file()
- prints basic stats to help debugging.

Run:
python3 scripts/tts_sim_test.py
"""
import os
import numpy as np
import soundfile as sf

# ensure project root in PYTHONPATH when running from repo root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.basereal import BaseReal


class DummyOpt:
    def __init__(self):
        self.fps = 30
        self.sessionid = 0
        self.tts = 'doubao'
        self.REF_FILE = ''
        self.REF_TEXT = None
        self.TTS_SERVER = 'http://127.0.0.1'
        self.customopt = []


def generate_sine(filename: str, duration_s=3.0, sr=16000, freq=220.0):
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    x = 0.3 * np.sin(2 * np.pi * freq * t)
    sf.write(filename, x, sr, subtype='PCM_16')
    return filename


def main():
    os.makedirs('data', exist_ok=True)
    wavpath = 'data/tts_test.wav'
    generate_sine(wavpath)
    print(f"Wrote synthetic TTS to {wavpath}")

    opt = DummyOpt()
    base = BaseReal(opt)
    # call put_audio_file to exercise chunking/put_audio_frame pipeline
    with open(wavpath, 'rb') as f:
        filebytes = f.read()
    try:
        base.put_audio_file(filebytes, {'test': True})
        print('put_audio_file executed, pending frames:', len(base._pending_audio))
    except Exception as e:
        print('Error calling put_audio_file:', e)


if __name__ == '__main__':
    main()
