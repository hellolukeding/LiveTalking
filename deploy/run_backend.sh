#!/bin/bash
cd /opt/2026/LiveTalking
export PYTHONPATH="/opt/2026/LiveTalking/src:/opt/2026/LiveTalking:/opt/2026/LiveTalking/wav2lip/models:/opt/2026/LiveTalking/src/main:/opt/2026/LiveTalking/src/core:/opt/2026/LiveTalking/src/utils:/opt/2026/LiveTalking/src/llm:/opt/2026/LiveTalking/src/services"
exec /opt/2026/LiveTalking/.venv/bin/python src/main/app.py "$@"
