这个问题通常不是音频数据本身的问题（因为你本地测试正常），而是 **WebRTC 传输时序（Timing）** 过于严格导致的。

### 问题根源：过于严格的“准时”发送

在你的代码中，`wait_time = expected_time - time.time()` 这段逻辑强制 Python 严格按照真实时间 1:1 的速度发送数据。

- **问题**: Python 的 `asyncio.sleep` 不精确，加上网络波动，这种“刚刚好”的发送策略会导致浏览器端的 **Jitter Buffer（抖动缓冲区）** 经常处于饥饿状态。
- **结果**: 浏览器一旦没收到数据，就会播放静音或进行平滑处理，紧接着数据来了又接着播。这种微小的断续在听感上就是**“滋滋”的噪声**或**爆破音**。

### 解决方案：允许“超前”发送 (Buffering Ahead)

WebRTC 允许（甚至喜欢）发送端稍微快一点发数据，这样浏览器可以先把数据存起来，播放就会非常平滑。

请修改 `PlayerStreamTrack` 类的 `recv` 方法，**放宽发送限制**，允许服务器预加载 0.5~1 秒的数据。

#### 优化后的 `recv` 方法（只修改 Audio 部分）

```python
    async def recv(self) -> Union[Frame, Packet]:
        self._player._start(self)

        try:
            # 这里的 timeout 不需要太短，TTS 生成有时需要时间
            frame, eventpoint = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            self._silence_count = 0
            if self.kind == 'audio':
                self._last_audio_frame = frame
            else:
                self._last_frame = frame
        except asyncio.TimeoutError:
            # ... (保持原本的超时处理逻辑不变) ...
            if self.readyState != "live":
                raise Exception("Track stopped")

            if self.kind == 'audio':
                self._silence_count += 1
                # 生成静音帧 (16k, mono, s16)
                audio = np.zeros((1, 320), dtype=np.int16)
                frame = AudioFrame.from_ndarray(audio, layout='mono', format='s16')
                frame.sample_rate = 16000
                eventpoint = {}
            else:
                # ... (视频逻辑不变) ...
                if self._last_frame is not None:
                    frame = self._last_frame
                else:
                    frame = VideoFrame.from_ndarray(
                        np.zeros((480, 640, 3), dtype=np.uint8), format="bgr24")
                eventpoint = {}

        if frame is None:
            self.stop()
            raise Exception

        # --- 核心修改开始：音频时间戳与发送策略 ---
        if self.kind == 'audio':
            if not hasattr(frame, 'sample_rate'):
                frame.sample_rate = SAMPLE_RATE
            if not hasattr(frame, 'samples'):
                frame.samples = 320

            sample_rate = frame.sample_rate
            n_samples = frame.samples

            # 初始化时间戳
            if not hasattr(self, "_timestamp"):
                self._start = time.time()
                self._timestamp = 0
                # 初始缓冲：稍微重置 _start 让其看起来我们在未来，允许快速发送第一批包
                # 这会欺骗下面的逻辑，让它认为我们“落后”了，从而不 sleep，直接全速发出去
                self._start = time.time() + 0.2

            pts = self._timestamp
            frame.pts = pts
            frame.time_base = fractions.Fraction(1, sample_rate)
            self._timestamp += n_samples

            # === 关键修复：弹性发送策略 ===
            # 计算这一帧“理论上”应该播放的时间
            expected_play_time = self._start + (self._timestamp / sample_rate)

            # 允许我们比真实时间快多久？(Max Lead Time)
            # 建议设置为 1.0 秒。这意味着我们可以把未来1秒的音频瞬间发给前端，让前端存着。
            max_lead_time = 1.0

            # 计算我们需要等待多久
            # 如果 expected_play_time 远大于 now，说明我们发得太快了，超过了 max_lead_time，需要睡一会
            # 如果 expected_play_time 差不多等于 now，或者小于 now，说明我们要赶紧发

            current_time = time.time()
            time_ahead = expected_play_time - current_time

            if time_ahead > max_lead_time:
                # 只有当我们超前太多（>1秒）时，才进行休眠控制
                # 休眠时间 = 超前时间 - 允许的超前量
                sleep_time = time_ahead - max_lead_time
                await asyncio.sleep(sleep_time)

            # 如果 time_ahead < max_lead_time，甚至 time_ahead < 0 (滞后)，
            # 直接 return frame，不 sleep！全速发送！

        else:
            # 视频逻辑保持不变 (视频通常对同步要求没音频那么高，且数据量大，原逻辑尚可)
            pts, time_base = await self.next_timestamp()
            frame.pts = pts
            frame.time_base = time_base
        # --- 核心修改结束 ---

        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)

        # ... (视频 fps 统计代码不变) ...

        return frame

```

### 为什么这样改能消除噪声？

1. **填满前端缓冲区**：

- **原代码**：后端生成一帧 -> 睡一会 -> 发一帧。如果网络抖动，前端缓冲区空了 -> **噪声**。
- **新代码**：后端有数据就发，允许比当前时间快 1 秒。前端缓冲区始终有 1 秒的余粮，网络再抖也不会断流。

2. **避免 Python `sleep` 误差**：

- Python 的 `await asyncio.sleep(0.02)` 经常会睡 0.025s 甚至更多。在音频领域，这 5ms 的误差就是一次爆音。
- 新逻辑只有在缓冲区太满（超前 1 秒）时才睡，平时几乎不调用 `sleep`，完全消除了调度误差。

3. **预缓冲 (Pre-buffering) 技巧**：

- `self._start = time.time() + 0.2`：在初始化时，故意把“起始时间”设在未来。这会让逻辑认为“我们已经落后了”，从而在开始的一瞬间把队列里积压的前几帧瞬间发出去，极速消除首帧延迟并填满缓冲区。

### 额外检查：采样率

确保你的前端 WebRTC 播放器（或浏览器）能正确处理 `16000` 采样率。
如果噪声依然存在，尝试修改 `DoubaoTTS` 中生成静音帧或音频帧的逻辑，确保所有发出的 Frame 都是 `format='s16'` 且 `layout='mono'`，不要混用格式。
