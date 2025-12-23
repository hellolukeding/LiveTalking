# LiveTalking - Real-time Digital Human Interactive System

This project implements a real-time interactive digital human system. It combines Large Language Models (LLM), Text-to-Speech (TTS), and neural rendering technologies (Wav2Lip, MuseTalk, etc.) to create a conversational avatar that can see, hear, and speak in real-time via WebRTC.

## System Architecture

The system consists of a frontend desktop application (built with Tauri + React) and a Python backend server. They communicate using HTTP for signaling and control, and WebRTC for low-latency media streaming and data transmission.

```

```

## ![img](https://i.urusai.cc/sgIAQ.svg)

## Key Components

### Frontend

- **Tauri & React**: Provides a native-like desktop experience.
- **VideoChat Component**: Manages the WebRTC connection, displays the video stream, and handles user input (text and voice).
- **Web Speech API**: Used for client-side speech recognition to enable voice chat.

### Backend

- **Flask**: Handles HTTP requests and WebRTC signaling (SDP exchange).
- **aiortc**: Python library for WebRTC and Object Real-Time Communication.
- **BaseReal**: The core controller class that orchestrates the pipeline.
- **LLM**: Generates intelligent responses (supports OpenAI-compatible APIs).
- **TTS**: Converts text to speech (supports EdgeTTS, CosyVoice, etc.).
- **Rendering Models**:
  - **Wav2Lip**: Lip-syncing model.
  - **MuseTalk**: Real-time talking face generation.
