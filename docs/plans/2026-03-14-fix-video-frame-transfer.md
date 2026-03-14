# Fix Video Frame Transfer in Session Process Isolation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix audio/video frame transfer from subprocess to main process in session isolation mode

**Architecture:**
- Subprocess runs LipReal rendering, generates frames
- basereal.py writes frames via `video_track._queue.put((frame, None))`
- Frames serialized and sent through multiprocessing.Queue to main process
- Main process QueueAudioTrack/QueueVideoTrack reads from mp.Queue and forwards to WebRTC

**Tech Stack:** Python multiprocessing, PyAV (AudioFrame/VideoFrame), aiortc, asyncio

**Root Cause:** Current implementation uses complex async wrapper chains that fail. `basereal.py` calls `asyncio.run_coroutine_threadsafe(track._queue.put(...))`, but the queue writing mechanism never executes properly in subprocess.

**Solution:** Simplify to direct synchronous queue writes with proper frame serialization in subprocess.

---

## Task 1: Create Frame Serialization Utilities

**Files:**
- Create: `src/main/frame_serializer.py`

**Step 1: Write frame serialization utilities**

```python
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
```

**Step 2: Verify file created**

Run: `ls -la src/main/frame_serializer.py`
Expected: File exists

**Step 3: Commit**

```bash
git add src/main/frame_serializer.py
git commit -m "feat(session-isolation): add frame serialization utilities"
```

---

## Task 2: Simplify subprocess frame handling

**Files:**
- Modify: `src/main/session_process.py:239-320`

**Step 1: Replace FakeTrack classes with direct queue writer**

```python
# In _session_main function, after "logger.info(f"[Session-{session_id}] LipReal initialized")"
# Replace the entire FakeTrack creation section with:

        # 创建直接队列写入器 - basereal.py 调用 _queue.put() 时直接序列化并写入 mp.Queue
        from frame_serializer import serialize_audio_frame, serialize_video_frame

        class DirectFrameWriter:
            """直接帧写入器 - 将帧序列化并写入 multiprocessing.Queue"""
            def __init__(self, mp_queue, frame_type):
                self.mp_queue = mp_queue
                self.frame_type = frame_type
                self.count = 0

            def put(self, frame_data):
                """同步写入方法 - basereal.py 直接调用这个"""
                try:
                    # frame_data 是 (frame, eventpoint) 元组
                    frame, eventpoint = frame_data if isinstance(frame_data, tuple) else (frame_data, None)

                    if frame is None:
                        return

                    # 序列化帧
                    if self.frame_type == 'audio':
                        serialized = serialize_audio_frame(frame)
                    else:
                        serialized = serialize_video_frame(frame)

                    # 写入 multiprocessing.Queue
                    self.mp_queue.put(serialized, block=False)

                    self.count += 1
                    if self.count % 50 == 0:
                        logger.info(f"[Session-{session_id}] {self.frame_type}: Put {self.count} frames")

                except Exception as e:
                    logger.error(f"[Session-{session_id}] {self.frame_type}.put() error: {e}")

        class FakeAudioTrack:
            """假的音频轨道 - _queue 是 DirectFrameWriter"""
            kind = "audio"

            def __init__(self, mp_queue):
                self._queue = DirectFrameWriter(mp_queue, 'audio')

            async def recv(self):
                raise StopIteration  # 这个方法不会被调用

        class FakeVideoTrack:
            """假的视频轨道 - _queue 是 DirectFrameWriter"""
            kind = "video"

            def __init__(self, mp_queue):
                self._queue = DirectFrameWriter(mp_queue, 'video')

            async def recv(self):
                raise StopIteration  # 这个方法不会被调用

        # 不再需要 ThreadQueue 和 frame_forwarder
        # 直接创建 FakeTrack，传递 multiprocessing.Queue
        fake_audio = FakeAudioTrack(audio_queue)
        fake_video = FakeVideoTrack(video_queue)

        logger.info(f"[Session-{session_id}] Using direct frame writers")
```

**Step 2: Remove frame_forwarder thread code**

Delete or comment out the entire `frame_forwarder` function and its thread creation (lines ~311-418). It's no longer needed since we write directly to mp.Queue.

**Step 3: Verify changes**

Run: `grep -n "DirectFrameWriter\|frame_forwarder" src/main/session_process.py`
Expected: DirectFrameWriter defined, frame_forwarder removed

**Step 4: Commit**

```bash
git add src/main/session_process.py
git commit -m "feat(session-isolation): use direct frame writers, remove frame_forwarder"
```

---

## Task 3: Update QueueAudioTrack/QueueVideoTrack to use new serializers

**Files:**
- Modify: `src/main/queue_track.py`

**Step 1: Add import for frame_serializer**

At the top of the file:
```python
from frame_serializer import deserialize_audio_frame, deserialize_video_frame
```

**Step 2: Update QueueAudioTrack.recv() method**

Replace the existing recv method (lines ~28-78) with:

```python
async def recv(self):
    """接收下一帧"""
    if self._stopped:
        raise StopIteration

    try:
        # 从队列获取序列化的帧数据
        frame_data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.queue.get(timeout=1.0)
        )

        if frame_data is None:
            logger.info(f"[QueueAudioTrack] Session {self.session_id} received end signal")
            self._stopped = True
            raise StopIteration

        # 使用 frame_serializer 反序列化
        audio_frame = deserialize_audio_frame(frame_data)

        self._timestamp += audio_frame.samples
        audio_frame.pts = self._timestamp
        audio_frame.time_base = "1/48000"
        return audio_frame

    except Exception as e:
        logger.error(f"[QueueAudioTrack] Error receiving frame: {e}")
        return AudioFrame(format='s16', layout='mono', samples=960)
```

**Step 3: Update QueueVideoTrack.recv() method**

Replace the existing recv method (lines ~94-144) with:

```python
async def recv(self):
    """接收下一帧"""
    if self._stopped:
        raise StopIteration

    try:
        # 从队列获取序列化的帧数据
        frame_data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.queue.get(timeout=1.0)
        )

        if frame_data is None:
            logger.info(f"[QueueVideoTrack] Session {self.session_id} received end signal")
            self._stopped = True
            raise StopIteration

        # 使用 frame_serializer 反序列化
        video_frame = deserialize_video_frame(frame_data)

        self._timestamp += 1
        video_frame.pts = self._timestamp
        video_frame.time_base = "1/90000"
        return video_frame

    except Exception as e:
        logger.error(f"[QueueVideoTrack] Error receiving frame: {e}")
        raise StopIteration
```

**Step 4: Verify changes**

Run: `grep "deserialize_.*_frame" src/main/queue_track.py`
Expected: Both deserialize_audio_frame and deserialize_video_frame imported and used

**Step 5: Commit**

```bash
git add src/main/queue_track.py
git commit -m "feat(session-isolation): use frame_serializer in queue tracks"
```

---

## Task 4: Remove ThreadQueue and frame_forwarder completely

**Files:**
- Modify: `src/main/session_process.py:223-226`

**Step 1: Remove ThreadQueue creation**

Remove these lines:
```python
audio_frame_queue = ThreadQueue(maxsize=100)
video_frame_queue = ThreadQueue(maxsize=100)
```

**Step 2: Delete frame_forwarder function and thread**

Find and delete the entire `def frame_forwarder():` function and its thread creation:
```python
forwarder_thread = Thread(target=frame_forwarder, daemon=True)
forwarder_thread.start()
```

**Step 3: Verify no references to ThreadQueue or frame_forwarder**

Run: `grep -n "ThreadQueue\|frame_forwarder" src/main/session_process.py`
Expected: Only in comments or removed

**Step 4: Commit**

```bash
git add src/main/session_process.py
git commit -m "refactor(session-isolation): remove ThreadQueue and frame_forwarder"
```

---

## Task 5: Test the fix

**Files:**
- Test: Manual testing via frontend

**Step 1: Clear Python cache**

Run: `find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete 2>/dev/null`
Expected: Cache cleared

**Step 2: Restart backend**

Run:
```bash
lsof -i :8011 | grep LISTEN | awk '{print $2}' | xargs -r kill -9
PYTHONPATH=/opt/2026/LiveTalking:/opt/2026/LiveTalking/wav2lip:/opt/2026/LiveTalking/src:/opt/2026/LiveTalking/src/core:/opt/2026/LiveTalking/src/main:/opt/2026/LiveTalking/src-utils /opt/2026/LiveTalking/.venv/bin/python src/main/app.py --listenport 8011 > /tmp/live_talking.log 2>&1 &
```
Expected: Service starts on port 8011

**Step 3: Connect from frontend and verify video frames**

1. Open frontend to http://192.168.1.132:8011/videochat
2. Select avatar_498cdabe
3. Click start button
4. Verify video displays in the video element

**Step 4: Check subprocess logs for frame transfer**

Run: `grep "Put.*frames" /tmp/session_*.log | tail -10`
Expected: Log entries like "[Session-XXX] video: Put 50 frames"

**Step 5: If successful, commit the working code**

```bash
git add .
git commit -m "fix(session-isolation): fix video frame transfer with direct serialization"
```

---

## Task 6: Document the solution

**Files:**
- Modify: `docs/plans/2026-03-14-session-process-isolation-design.md`

**Step 1: Update architecture documentation**

Add section explaining the final frame transfer mechanism:

```markdown
## Frame Transfer Mechanism

The final implementation uses direct synchronous writes:

1. basereal.py calls `video_track._queue.put((frame, None))`
2. DirectFrameWriter.put() immediately serializes the frame
3. Serialized frame written directly to multiprocessing.Queue
4. Main process QueueVideoTrack reads and deserializes
5. Frame sent to WebRTC

This eliminates:
- ThreadQueue intermediate layer
- frame_forwarder thread
- Complex async wrapper chains
```

**Step 2: Commit**

```bash
git add docs/plans/2026-03-14-session-process-isolation-design.md
git commit -m "docs(session-isolation): document final frame transfer mechanism"
```

---

## Success Criteria

- ✅ Frontend shows video frames when connected
- ✅ Subprocess logs show "Put X frames" messages
- ✅ No frame_forwarder thread in subprocess
- ✅ Direct synchronous queue writes working
- ✅ Frame serialization/deserialization working
