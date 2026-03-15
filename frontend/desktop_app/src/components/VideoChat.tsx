import {
    AudioMutedOutlined,
    AudioOutlined,
    LeftOutlined,
    MessageOutlined,
    PhoneOutlined,
    SettingOutlined,
    SoundOutlined,
    UserOutlined,
} from '@ant-design/icons';
import { message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { negotiateOffer, sendHumanMessage } from '../api';
import { getApiBaseUrl } from '../api/client';
import ChatSidebar, { ChatMessage } from './ChatSidebar';
import Settings from './Settings';

// Avatar ID validation function
const isValidAvatarId = (id: string | null): id is string => {
    if (!id) return false;
    return /^[a-zA-Z0-9_-]+$/.test(id);
};

// ========== 对话状态机 ==========
// 状态转换流程: IDLE -> LISTENING -> LLM_PROCESSING -> TTS_PLAYING -> LISTENING
//                          ^______________________________| (循环)
enum ConversationState {
    IDLE = 'IDLE',                      // 空闲状态
    LISTENING = 'LISTENING',            // 正在监听用户语音（ASR工作）
    LLM_PROCESSING = 'LLM_PROCESSING',  // LLM正在处理（ASR暂停/缓冲）
    TTS_PLAYING = 'TTS_PLAYING'         // AI正在说话（ASR暂停/缓冲）
}

// ASR 缓冲区结构（用于在LLM处理期间缓冲音频）
interface ASRBuffer {
    audioBlob: Blob;
    timestamp: number;
}

const TTS_FALLBACK_TIMEOUT_MS = 2500;
const USE_WEBRTC_UPSTREAM_ASR = true;

export default function VideoChat() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const avatarId = searchParams.get('avatar_id');

    useEffect(() => {
        if (!isValidAvatarId(avatarId)) {
            navigate('/select-avatar', { replace: true });
            return;
        }
    }, [avatarId, navigate]);

    const [sessionId, setSessionId] = useState<string>('0');
    const [isStarted, setIsStarted] = useState(false);
    const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
    const [isChatOpen, setIsChatOpen] = useState(false);
    const [callDuration, setCallDuration] = useState(0);
    const [isLoading, setIsLoading] = useState(false);

    const videoRef = useRef<HTMLVideoElement>(null);
    const localVideoRef = useRef<HTMLVideoElement>(null);
    const audioRef = useRef<HTMLAudioElement>(null);
    const pcRef = useRef<RTCPeerConnection | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const durationRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const localStreamRef = useRef<MediaStream | null>(null);

    const [isVoiceChatOn, setIsVoiceChatOn] = useState(false);
    const [isSpeakerOn, setIsSpeakerOn] = useState(true);
    const [isCameraOn, setIsCameraOn] = useState(false);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);

    // ========== 对话状态管理 ==========
    const [conversationState, setConversationState] = useState<ConversationState>(ConversationState.IDLE);
    const conversationStateRef = useRef<ConversationState>(ConversationState.IDLE);
    const aiSpeakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const llmProcessingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // ASR 相关
    const recognitionRef = useRef<any>(null);
    const micPermissionStreamRef = useRef<MediaStream | null>(null);
    const isRequestingMicPermissionRef = useRef(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const asrMimeTypeRef = useRef<string>('audio/webm');
    const asrIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const asrBufferRef = useRef<ASRBuffer[]>([]);  // ASR 缓冲区
    const asrFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const asrRequestInFlightRef = useRef(false);
    const asrQueuedBlobRef = useRef<Blob | null>(null);
    const lastAsrResultRef = useRef<{ text: string; ts: number } | null>(null);
    const lastAssistantSnapshotRef = useRef<{ text: string; ts: number } | null>(null);
    const upstreamAudioSenderRef = useRef<RTCRtpSender | null>(null);
    const upstreamMicTrackRef = useRef<MediaStreamTrack | null>(null);

    // 兼容旧的 isAISpeaking（用于UI显示）
    const isAISpeaking = conversationState === ConversationState.TTS_PLAYING;

    // ========== 同步状态到 ref（用于闭包访问） ==========
    useEffect(() => {
        conversationStateRef.current = conversationState;
        console.log('[State] Conversation state:', conversationState);
    }, [conversationState]);

    // ========== 状态转换函数 ==========
    const setStateListening = () => {
        console.log('[State] -> LISTENING (ASR enabled)');
        setConversationState(ConversationState.LISTENING);

        if (aiSpeakingTimeoutRef.current) {
            clearTimeout(aiSpeakingTimeoutRef.current);
            aiSpeakingTimeoutRef.current = null;
        }
        if (llmProcessingTimeoutRef.current) {
            clearTimeout(llmProcessingTimeoutRef.current);
            llmProcessingTimeoutRef.current = null;
        }

        // 处理缓冲的音频（仅本地分片 ASR 模式需要）
        if (!USE_WEBRTC_UPSTREAM_ASR && asrBufferRef.current.length > 0) {
            const buffers = [...asrBufferRef.current];
            asrBufferRef.current = [];
            const latestBuffer = buffers[buffers.length - 1];
            console.log('[State] Processing buffered audio:', buffers.length, 'chunks, latest size:', latestBuffer.audioBlob.size);
            sendAudioToBackend(latestBuffer.audioBlob);
        }
    };
    const setStateLLMProcessing = () => {
        console.log('[State] -> LLM_PROCESSING (ASR paused, buffering enabled)');
        setConversationState(ConversationState.LLM_PROCESSING);
        // 设置超时保护，如果30秒没有响应，回到监听状态
        if (llmProcessingTimeoutRef.current) {
            clearTimeout(llmProcessingTimeoutRef.current);
        }
        llmProcessingTimeoutRef.current = setTimeout(() => {
            console.warn('[State] LLM processing timeout, returning to LISTENING');
            setStateListening();
        }, 30000);
    };

    const setStateTTSPlaying = () => {
        console.log('[State] -> TTS_PLAYING (ASR paused, buffering enabled)');
        setConversationState(ConversationState.TTS_PLAYING);
        // 清除 LLM 超时
        if (llmProcessingTimeoutRef.current) {
            clearTimeout(llmProcessingTimeoutRef.current);
        }
        // 重置并设置超时保护（1秒后如果没有新消息，则认为AI停止说话）
        if (aiSpeakingTimeoutRef.current) {
            clearTimeout(aiSpeakingTimeoutRef.current);
        }
        aiSpeakingTimeoutRef.current = setTimeout(() => {
            console.log('[State] AI stopped speaking (fallback timeout)');
            setStateListening();
        }, TTS_FALLBACK_TIMEOUT_MS);
    };

    const extendTTSPlaying = () => {
        // 延长 TTS 播放状态（在收到新的AI消息时调用）
        if (conversationStateRef.current === ConversationState.TTS_PLAYING) {
            if (aiSpeakingTimeoutRef.current) {
                clearTimeout(aiSpeakingTimeoutRef.current);
            }
            aiSpeakingTimeoutRef.current = setTimeout(() => {
                console.log('[State] AI stopped speaking (fallback timeout after extend)');
                setStateListening();
            }, TTS_FALLBACK_TIMEOUT_MS);
        }
    };

    // ========== 清理定时器 ==========
    useEffect(() => {
        return () => {
            if (aiSpeakingTimeoutRef.current) {
                clearTimeout(aiSpeakingTimeoutRef.current);
            }
            if (llmProcessingTimeoutRef.current) {
                clearTimeout(llmProcessingTimeoutRef.current);
            }
            if (asrFlushTimerRef.current) {
                clearTimeout(asrFlushTimerRef.current);
            }
        };
    }, []);

    // ========== ASR 缓冲区管理 ==========
    const MIN_ASR_BLOB_BYTES = 320;
    const ASR_DUPLICATE_WINDOW_MS = 2500;
    const ASR_ECHO_GUARD_WINDOW_MS = 5000;

    const normalizeText = (text: string): string =>
        text
            .toLowerCase()
            .replace(/[\s，。！？、,.!?;:：；"'“”‘’（）()【】\[\]-]/g, '')
            .trim();

    const blobToBase64 = (audioBlob: Blob): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                try {
                    const base64 = (reader.result as string).split(',')[1];
                    resolve(base64);
                } catch (error) {
                    reject(error);
                }
            };
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(audioBlob);
        });
    };

    const flushASRBuffer = () => {
        if (asrBufferRef.current.length === 0) return;

        const buffers = [...asrBufferRef.current];
        asrBufferRef.current = [];
        const latestBuffer = buffers[buffers.length - 1];
        console.log('[ASR] Flushing buffered audio:', buffers.length, 'chunks, latest:', latestBuffer.audioBlob.size, 'bytes');
        sendAudioToBackend(latestBuffer.audioBlob);
    };

    const isLikelyEchoFromAssistant = (text: string): boolean => {
        const current = normalizeText(text);
        if (!current || current.length < 4) {
            return false;
        }

        const last = lastAssistantSnapshotRef.current;
        if (!last) {
            return false;
        }

        const ageMs = Date.now() - last.ts;
        if (ageMs > ASR_ECHO_GUARD_WINDOW_MS) {
            return false;
        }

        const assistant = normalizeText(last.text);
        if (!assistant || assistant.length < 4) {
            return false;
        }

        return assistant.includes(current) || current.includes(assistant);
    };

    // 格式化通话时长
    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    useEffect(() => {
        if (isStarted) {
            durationRef.current = setInterval(() => {
                setCallDuration(prev => prev + 1);
            }, 1000);
        } else {
            if (durationRef.current) {
                clearInterval(durationRef.current);
                durationRef.current = null;
            }
            setCallDuration(0);
        }
        return () => {
            if (durationRef.current) {
                clearInterval(durationRef.current);
            }
        };
    }, [isStarted]);

    const logAudioDevices = (devices: MediaDeviceInfo[]) => {
        const audioInputs = devices.filter(device => device.kind === 'audioinput');
        const audioOutputs = devices.filter(device => device.kind === 'audiooutput');
        const videoInputs = devices.filter(device => device.kind === 'videoinput');

        console.log('[ASR] ========== Device Enumeration ==========');
        console.log('[ASR] Audio Input devices (microphones):', audioInputs.length);
        audioInputs.forEach((device, index) => {
            console.log(`  [${index}] ${device.label || '(无标签)'} (ID: ${device.deviceId})`);
        });
        console.log('[ASR] Audio Output devices (speakers):', audioOutputs.length);
        audioOutputs.forEach((device, index) => {
            console.log(`  [${index}] ${device.label || '(无标签)'}`);
        });
        console.log('[ASR] Video Input devices (cameras):', videoInputs.length);
        videoInputs.forEach((device, index) => {
            console.log(`  [${index}] ${device.label || '(无标签)'}`);
        });
        console.log('[ASR] ========================================');

        if (audioInputs.length === 0) {
            console.warn('[ASR] ❌ No audio input devices found!');
            message.error({
                content: '未检测到麦克风设备。请检查系统麦克风权限与设备占用情况',
                duration: 8
            });
        } else {
            console.log('[ASR] ✓ Found audio input devices');
        }
    };

    const ensureMicStream = async (): Promise<MediaStream> => {
        const current = micPermissionStreamRef.current;
        if (current) {
            const liveTrack = current.getAudioTracks().find(track => track.readyState === 'live');
            if (liveTrack) {
                return current;
            }
            current.getTracks().forEach(track => track.stop());
            micPermissionStreamRef.current = null;
        }

        const preferredConstraints: MediaStreamConstraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
                sampleRate: 48000,
                sampleSize: 16,
            }
        };

        try {
            return await navigator.mediaDevices.getUserMedia(preferredConstraints);
        } catch (error: any) {
            if (error?.name !== 'OverconstrainedError') {
                throw error;
            }
            return navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                }
            });
        }
    };

    const attachUpstreamAudioTrack = async (stream: MediaStream) => {
        const track = stream.getAudioTracks()[0];
        if (!track) {
            throw new Error('未获取到麦克风音轨');
        }

        let sender = upstreamAudioSenderRef.current;
        if (!sender) {
            for (let i = 0; i < 20; i += 1) {
                await new Promise(resolve => setTimeout(resolve, 50));
                sender = upstreamAudioSenderRef.current;
                if (sender) {
                    break;
                }
            }
        }

        if (!sender) {
            throw new Error('WebRTC 上行音轨未就绪');
        }

        await sender.replaceTrack(track);
        upstreamMicTrackRef.current = track;
        setStateListening();
        console.log('[ASR] WebRTC upstream ASR started');
    };

    useEffect(() => {
        let cancelled = false;

        const startASR = async () => {
            if (!isVoiceChatOn || !isStarted) {
                stopBackendASR();
                return;
            }

            if (isRequestingMicPermissionRef.current) {
                console.log('[ASR] Already requesting microphone permission, skipping...');
                return;
            }
            isRequestingMicPermissionRef.current = true;
            message.loading({ content: '正在请求麦克风权限...', key: 'micPermission', duration: 10 });

            try {
                if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    throw new Error('麦克风不可用：需要通过 HTTPS 或 localhost 访问');
                }

                const devices = await navigator.mediaDevices.enumerateDevices();
                if (cancelled) {
                    return;
                }
                logAudioDevices(devices);

                const stream = await ensureMicStream();
                if (cancelled) {
                    stream.getTracks().forEach(track => track.stop());
                    return;
                }

                micPermissionStreamRef.current = stream;
                message.success({ content: '麦克风权限已授予', key: 'micPermission', duration: 2 });
                console.log('[ASR] Microphone permission granted');

                if (USE_WEBRTC_UPSTREAM_ASR) {
                    await attachUpstreamAudioTrack(stream);
                    message.info('语音识别已启动（WebRTC 上行）');
                } else {
                    initBackendASR(stream);
                }
            } catch (err: any) {
                if (!cancelled) {
                    setIsVoiceChatOn(false);
                }

                if (err?.name === 'NotAllowedError') {
                    message.error({ content: '麦克风权限被拒绝，请允许麦克风访问以使用语音识别功能', key: 'micPermission', duration: 5 });
                    message.warning({
                        content: '请点击地址栏左侧锁图标，允许麦克风访问',
                        duration: 6
                    });
                } else if (err?.name === 'NotFoundError') {
                    message.error({ content: '未检测到麦克风设备，请连接麦克风后重试', key: 'micPermission', duration: 5 });
                } else {
                    message.error({ content: `麦克风访问失败: ${err?.message || err?.name || '未知错误'}`, key: 'micPermission', duration: 5 });
                }
                console.error('[ASR] Failed to start microphone:', err);
            } finally {
                isRequestingMicPermissionRef.current = false;
            }
        };

        startASR();
        return () => {
            cancelled = true;
            stopBackendASR();
        };
    }, [isVoiceChatOn, isStarted]);

    // 初始化后端腾讯 ASR
    const initBackendASR = (stream: MediaStream) => {
        try {
            // 检测支持的音频格式
            const mimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/ogg',
                'audio/mp4',
            ];

            let selectedMimeType = '';
            for (const mimeType of mimeTypes) {
                if (MediaRecorder.isTypeSupported(mimeType)) {
                    selectedMimeType = mimeType;
                    console.log('[ASR] Using mimeType:', mimeType);
                    break;
                }
            }

            if (!selectedMimeType) {
                console.error('[ASR] No supported audio mimeType found');
                message.error('浏览器不支持音频录制');
                setIsVoiceChatOn(false);
                return;
            }

            // 使用 MediaRecorder 录制音频
            const mediaRecorder = new MediaRecorder(stream, {
                mimeType: selectedMimeType,
            });

            // 记录实际使用的 mimeType
            console.log('[ASR] MediaRecorder actual mimeType:', mediaRecorder.mimeType);

            mediaRecorder.ondataavailable = (event) => {
                if (!event.data || event.data.size <= 0) {
                    return;
                }

                const audioBlob = new Blob([event.data], { type: selectedMimeType });
                console.log('[ASR] Blob size:', audioBlob.size, 'type:', audioBlob.type, 'state:', conversationStateRef.current);

                if (conversationStateRef.current === ConversationState.LISTENING) {
                    asrBufferRef.current.push({
                        audioBlob: audioBlob,
                        timestamp: Date.now()
                    });

                    if (asrFlushTimerRef.current) {
                        clearTimeout(asrFlushTimerRef.current);
                    }

                    asrFlushTimerRef.current = setTimeout(() => {
                        if (asrBufferRef.current.length > 0) {
                            const buffers = [...asrBufferRef.current];
                            asrBufferRef.current = [];

                            const latestBuffer = buffers[buffers.length - 1];
                            console.log('[ASR] Silence detected, sending latest audio:', latestBuffer.audioBlob.size, 'bytes from', buffers.length, 'chunks');
                            sendAudioToBackend(latestBuffer.audioBlob);
                        }
                    }, 320);
                } else if (conversationStateRef.current === ConversationState.LLM_PROCESSING ||
                    conversationStateRef.current === ConversationState.TTS_PLAYING) {
                    console.log('[ASR] State=' + conversationStateRef.current + ', buffering audio');
                    asrBufferRef.current.push({
                        audioBlob: audioBlob,
                        timestamp: Date.now()
                    });
                    if (asrBufferRef.current.length > 25) {
                        asrBufferRef.current.shift();
                    }
                }
            };

            // 保存引用和 mimeType
            mediaRecorderRef.current = mediaRecorder;
            asrMimeTypeRef.current = selectedMimeType;

            // 开始录音（使用 timeslice 连续切片，避免 stop/start 造成漏词）
            const startRecording = () => {
                if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'inactive') {
                    mediaRecorderRef.current.start(280);
                }
            };

            // 第一次开始录音
            startRecording();

            asrIntervalRef.current = null;

            // 设置初始状态为 LISTENING
            setStateListening();

            console.log('[ASR] Backend Tencent ASR started');
            message.info('语音识别已启动（使用腾讯 ASR）');
        } catch (e) {
            console.error('[ASR] Failed to start backend ASR:', e);
            message.error('无法启动语音识别');
            setIsVoiceChatOn(false);
        }
    };

    const recognizeAudioBlob = async (audioBlob: Blob): Promise<string | null> => {
        if (!audioBlob || audioBlob.size < MIN_ASR_BLOB_BYTES) {
            return null;
        }
        try {
            const base64Audio = await blobToBase64(audioBlob);
            const apiBaseUrl = getApiBaseUrl();
            const response = await fetch(`${apiBaseUrl}/speech_recognize`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ audio: base64Audio }),
            });

            const result = await response.json();
            if (result.code !== 0) {
                console.warn('[ASR] Recognition failed:', result.msg);
                return null;
            }

            const text = String(result.data?.text || '').trim();
            return text || null;
        } catch (e) {
            console.error('[ASR] Failed to recognize audio:', e);
            return null;
        }
    };

    // 发送音频到后端（带串行队列，避免并发请求相互覆盖）
    const sendAudioToBackend = (audioBlob: Blob) => {
        if (!audioBlob || audioBlob.size < MIN_ASR_BLOB_BYTES) {
            return;
        }

        // 避免并发 ASR 请求导致“第一句后第二句丢失”
        if (asrRequestInFlightRef.current) {
            asrQueuedBlobRef.current = audioBlob;
            return;
        }

        asrRequestInFlightRef.current = true;
        (async () => {
            try {
                const text = await recognizeAudioBlob(audioBlob);
                if (text) {
                    const now = Date.now();
                    const last = lastAsrResultRef.current;
                    if (last && last.text === text && now - last.ts < ASR_DUPLICATE_WINDOW_MS) {
                        return;
                    }
                    if (isLikelyEchoFromAssistant(text)) {
                        console.log('[ASR] Dropped likely echo from assistant:', text);
                        return;
                    }
                    lastAsrResultRef.current = { text, ts: now };
                    console.log('[ASR] Tencent ASR recognized:', text);
                    await handleSendMessage(text, { interrupt: false, source: 'asr' });
                }
            } finally {
                asrRequestInFlightRef.current = false;
                const queuedBlob = asrQueuedBlobRef.current;
                asrQueuedBlobRef.current = null;
                if (queuedBlob) {
                    setTimeout(() => sendAudioToBackend(queuedBlob), 0);
                }
            }
        })();
    };

    // 发送音频到后端进行识别（保留这个函数以防被其他地方调用）
    // 停止后端 ASR
    const stopBackendASR = () => {
        // 仅本地分片 ASR 模式需要 flush。WebRTC 上行模式直接丢弃本地缓存。
        if (!USE_WEBRTC_UPSTREAM_ASR && asrBufferRef.current.length > 0) {
            flushASRBuffer();
        }
        asrBufferRef.current = [];

        asrRequestInFlightRef.current = false;
        asrQueuedBlobRef.current = null;
        lastAsrResultRef.current = null;
        lastAssistantSnapshotRef.current = null;

        // 停止定时器
        if (asrIntervalRef.current) {
            clearInterval(asrIntervalRef.current);
            asrIntervalRef.current = null;
        }
        if (asrFlushTimerRef.current) {
            clearTimeout(asrFlushTimerRef.current);
            asrFlushTimerRef.current = null;
        }

        // 停止录音
        if (mediaRecorderRef.current) {
            try {
                if (mediaRecorderRef.current.state !== 'inactive') {
                    mediaRecorderRef.current.stop();
                }
            } catch (e) {
                console.warn('[ASR] stop mediaRecorder failed:', e);
            } finally {
                mediaRecorderRef.current = null;
            }
        }

        // 停止 WebRTC 上行麦克风轨道
        if (upstreamAudioSenderRef.current) {
            upstreamAudioSenderRef.current.replaceTrack(null).catch((err) => {
                console.warn('[ASR] detach upstream mic track failed:', err);
            });
        }
        if (upstreamMicTrackRef.current) {
            try {
                upstreamMicTrackRef.current.stop();
            } catch {
                // ignore
            }
            upstreamMicTrackRef.current = null;
        }

        // 清理音频流
        if (micPermissionStreamRef.current) {
            micPermissionStreamRef.current.getTracks().forEach(track => track.stop());
            micPermissionStreamRef.current = null;
        }

        // 停止 Web Speech API（如果存在）
        if (recognitionRef.current) {
            recognitionRef.current.stop();
            recognitionRef.current = null;
        }

        console.log('[ASR] Backend ASR stopped');
    };

    const resetTimer = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (isStarted) {
            timerRef.current = setTimeout(() => {
                message.info('长时间未操作，已自动断开连接');
                stop();
            }, 60000);
        }
    };

    // ========== 标记AI开始说话（由data channel消息触发） ==========
    const markAISpeaking = () => {
        // 如果当前是 LLM_PROCESSING 状态，转换到 TTS_PLAYING
        // 如果已经是 TTS_PLAYING，延长超时时间
        if (conversationStateRef.current === ConversationState.LLM_PROCESSING) {
            setStateTTSPlaying();
        } else if (conversationStateRef.current === ConversationState.TTS_PLAYING) {
            extendTTSPlaying();
        } else {
            // 其他状态也转换为 TTS_PLAYING
            setStateTTSPlaying();
        }
    };

    const appendAssistantText = (textChunk: string) => {
        const text = (textChunk || '').trim();
        if (!text) return;
        markAISpeaking();
        lastAssistantSnapshotRef.current = { text: textChunk, ts: Date.now() };
        setChatHistory(prev => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
                return [
                    ...prev.slice(0, -1),
                    { ...lastMsg, content: lastMsg.content + textChunk }
                ];
            }
            return [...prev, {
                role: 'assistant' as const,
                content: textChunk,
                timestamp: Date.now()
            }];
        });
    };

    const start = async () => {
        if (isStarted || isLoading) return;

        setIsLoading(true);

        // 先开启本地摄像头（仅在 HTTPS 或 localhost 环境下可用）
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user' },
                    audio: false
                });
                localStreamRef.current = stream;
                if (localVideoRef.current) {
                    localVideoRef.current.srcObject = stream;
                }
                setIsCameraOn(true);
            } catch (err) {
                console.warn('无法获取摄像头（非HTTPS环境或权限被拒绝）:', err);
                // 摄像头获取失败不阻止通话
            }
        } else {
            console.warn('navigator.mediaDevices 不可用（需要 HTTPS 或 localhost）');
        }

        // 配置 ICE 服务器以改善 NAT 穿透
        const config: RTCConfiguration = {
            sdpSemantics: 'unified-plan',
            iceServers: [
                { urls: 'stun:stun.qq.com:3478' },
            ]
        } as any;

        const pc = new RTCPeerConnection(config);
        pcRef.current = pc;

        const dc = pc.createDataChannel("chat");
        dc.onmessage = (event) => {
            const raw = typeof event.data === 'string' ? event.data : String(event.data ?? '');
            if (!raw) return;

            // 优先处理 JSON eventpoint（TTS start/end）
            if (raw.startsWith('{') && raw.endsWith('}')) {
                try {
                    const parsed = JSON.parse(raw);
                    if (parsed && typeof parsed === 'object') {
                        if (parsed.status === 'start') {
                            markAISpeaking();
                            return;
                        }
                        if (parsed.status === 'end') {
                            console.log('[DataChannel] Received TTS end signal:', parsed);
                            setStateListening();
                            return;
                        }
                    }
                } catch {
                    // 非 JSON 文本，按普通消息处理
                }
            }

            // ASR_RESULT 属于状态/调试消息，不应追加到 assistant 回复
            if (raw.startsWith('ASR_RESULT:')) {
                if (USE_WEBRTC_UPSTREAM_ASR) {
                    const text = raw.replace(/^ASR_RESULT:/, '').trim();
                    if (!text) {
                        return;
                    }

                    const now = Date.now();
                    const last = lastAsrResultRef.current;
                    if (last && last.text === text && now - last.ts < ASR_DUPLICATE_WINDOW_MS) {
                        return;
                    }
                    if (isLikelyEchoFromAssistant(text)) {
                        console.log('[ASR] Dropped likely echo from assistant:', text);
                        return;
                    }
                    lastAsrResultRef.current = { text, ts: now };

                    setChatHistory(prev => [...prev, {
                        role: 'user',
                        content: text,
                        timestamp: now
                    }]);
                    setStateLLMProcessing();
                }
                return;
            }

            appendAssistantText(raw);
        };

        pc.addEventListener('track', (evt) => {
            if (evt.track.kind === 'video') {
                if (videoRef.current) {
                    videoRef.current.srcObject = evt.streams[0];
                }
            } else {
                if (audioRef.current) {
                    audioRef.current.srcObject = evt.streams[0];
                }
            }
        });

        pc.addTransceiver('video', { direction: 'recvonly' });
        const upstreamAudioTransceiver = pc.addTransceiver('audio', {
            direction: USE_WEBRTC_UPSTREAM_ASR ? 'sendrecv' : 'recvonly'
        });
        upstreamAudioSenderRef.current = upstreamAudioTransceiver.sender ?? null;

        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);

            await new Promise<void>((resolve) => {
                if (pc.iceGatheringState === 'complete') {
                    resolve();
                } else {
                    let timeoutId = setTimeout(() => {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        console.log("ICE gathering timed out after 1500ms, proceeding with gathered candidates.");
                        resolve();
                    }, 1500);

                    const checkState = () => {
                        if (pc.iceGatheringState === 'complete') {
                            clearTimeout(timeoutId);
                            pc.removeEventListener('icegatheringstatechange', checkState);
                            resolve();
                        }
                    };
                    pc.addEventListener('icegatheringstatechange', checkState);
                }
            });

            const answer = await negotiateOffer({
                sdp: pc.localDescription?.sdp,
                type: pc.localDescription?.type,
                avatar_id: avatarId || '',
            });

            setSessionId(answer.sessionid);
            await pc.setRemoteDescription(answer);
            setIsStarted(true);
            setIsLoading(false);

        } catch (e) {
            console.error(e);
            message.error('连接失败: ' + e);
            // 连接失败时关闭摄像头
            if (localStreamRef.current) {
                localStreamRef.current.getTracks().forEach(track => track.stop());
                localStreamRef.current = null;
            }
            setIsCameraOn(false);
            setIsLoading(false);
        }
    };

    const stop = () => {
        stopBackendASR();

        if (pcRef.current) {
            pcRef.current.close();
            pcRef.current = null;
        }
        upstreamAudioSenderRef.current = null;
        upstreamMicTrackRef.current = null;

        // 关闭本地摄像头
        if (localStreamRef.current) {
            localStreamRef.current.getTracks().forEach(track => track.stop());
            localStreamRef.current = null;
        }
        setIsCameraOn(false);
        setIsStarted(false);
    };

    const handleSendMessage = async (
        text: string,
        options?: { interrupt?: boolean; source?: 'user' | 'asr' }
    ) => {
        const interrupt = options?.interrupt ?? true;
        resetTimer();
        setChatHistory(prev => [...prev, {
            role: 'user',
            content: text,
            timestamp: Date.now()
        }]);

        // 设置状态为 LLM_PROCESSING（ASR将暂停并缓冲音频）
        setStateLLMProcessing();

        try {
            await sendHumanMessage(text, sessionId, interrupt);
        } catch (e) {
            console.error(e);
            message.error('发送失败');
            // 发送失败，回到监听状态
            setStateListening();
        }
    };

    const toggleSpeaker = () => {
        setIsSpeakerOn(!isSpeakerOn);
        if (audioRef.current) {
            audioRef.current.muted = isSpeakerOn;
        }
    };

    // 开启/关闭本地摄像头
    const toggleCamera = async () => {
        if (isCameraOn) {
            // 关闭摄像头
            if (localStreamRef.current) {
                localStreamRef.current.getTracks().forEach(track => track.stop());
                localStreamRef.current = null;
            }
            if (localVideoRef.current) {
                localVideoRef.current.srcObject = null;
            }
            setIsCameraOn(false);
        } else {
            // 检查 mediaDevices 是否可用
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                message.error('摄像头不可用（需要 HTTPS 或 localhost 访问）');
                return;
            }
            // 开启摄像头
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user' },
                    audio: false
                });
                localStreamRef.current = stream;
                if (localVideoRef.current) {
                    localVideoRef.current.srcObject = stream;
                }
                setIsCameraOn(true);
            } catch (err) {
                console.error('无法获取摄像头', err);
                message.error('无法获取摄像头权限');
            }
        }
    };

    useEffect(() => {
        resetTimer();
        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [isStarted]);

    // 当 isStarted 变为 true 且有本地流时，绑定到 video 元素
    useEffect(() => {
        if (isStarted && isCameraOn && localStreamRef.current && localVideoRef.current) {
            localVideoRef.current.srcObject = localStreamRef.current;
        }
    }, [isStarted, isCameraOn]);

    useEffect(() => {
        return () => {
            stop();
            // 清理所有定时器
            if (aiSpeakingTimeoutRef.current) {
                clearTimeout(aiSpeakingTimeoutRef.current);
            }
            if (llmProcessingTimeoutRef.current) {
                clearTimeout(llmProcessingTimeoutRef.current);
            }
            if (asrFlushTimerRef.current) {
                clearTimeout(asrFlushTimerRef.current);
            }
            // 清理后端 ASR 资源
            stopBackendASR();
        }
    }, []);

    return (
        <div
            className="relative w-full h-full bg-[#ededed] overflow-hidden"
            onMouseMove={resetTimer}
            onClick={resetTimer}
        >
            {/* 左上角：形象管理入口 */}
            <div className="absolute top-4 left-4 z-20">
                <button
                    onClick={() => navigate('/avatars')}
                    title="数字人形象管理"
                    style={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        backgroundColor: 'rgba(255,255,255,0.85)',
                        border: 'none',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.1)')}
                    onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
                >
                    <UserOutlined style={{ fontSize: 18, color: '#5b4aff' }} />
                </button>
            </div>

            {/* 顶部通话时长和状态 */}
            {isStarted && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3">
                    <span className="text-gray-600 text-sm">{formatDuration(callDuration)}</span>
                    {isAISpeaking && (
                        <span className="px-2 py-1 bg-green-500 text-white text-xs rounded-full animate-pulse">
                            AI 正在说话
                        </span>
                    )}
                    {isVoiceChatOn && !isAISpeaking && (
                        <span className="px-2 py-1 bg-blue-500 text-white text-xs rounded-full">
                            麦克风开启
                        </span>
                    )}
                </div>
            )}

            {/* 主视频区域 */}
            <div className="absolute inset-0 z-0">
                {!isStarted && !isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-[#ededed] z-10">
                        <div className="text-center">
                            <div className="w-32 h-32 mx-auto mb-6 rounded-full bg-gray-300 flex items-center justify-center overflow-hidden">
                                <span className="text-6xl">🤖</span>
                            </div>
                            <div className="text-xl text-gray-700 mb-2">AI 助手</div>
                            <div className="text-gray-500 text-sm">等待接听...</div>
                        </div>
                    </div>
                )}
                {isLoading && !isStarted && (
                    <div className="absolute inset-0 flex items-center justify-center bg-[#ededed] z-10">
                        <div className="text-center">
                            {/* Loading 动画 */}
                            <div className="relative w-32 h-32 mx-auto mb-6">
                                <div className="absolute inset-0 rounded-full border-4 border-gray-200"></div>
                                <div className="absolute inset-0 rounded-full border-4 border-t-green-500 border-r-transparent border-b-transparent border-l-transparent animate-spin"></div>
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <span className="text-5xl">🤖</span>
                                </div>
                            </div>
                            <div className="text-xl text-gray-700 mb-2">正在连接中...</div>
                            <div className="text-gray-500 text-sm">请稍候，正在建立连接</div>
                        </div>
                    </div>
                )}
                <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    className="w-full h-full object-cover"
                    style={{ display: isStarted ? 'block' : 'none' }}
                />
                <audio ref={audioRef} autoPlay />
            </div>

            {/* 右上角小窗口（本地摄像头画面） */}
            {isStarted && (
                <div
                    className="absolute top-12 right-4 w-24 h-32 bg-gray-800 overflow-hidden shadow-lg z-20 cursor-pointer"
                    style={{ borderRadius: 8, border: '2px solid white' }}
                    onClick={toggleCamera}
                >
                    <video
                        ref={localVideoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-full object-cover"
                        style={{
                            transform: 'scaleX(-1)',
                            display: isCameraOn ? 'block' : 'none'
                        }}
                    />
                    {!isCameraOn && (
                        <div className="w-full h-full flex flex-col items-center justify-center bg-gray-700">
                            <span className="text-2xl mb-1">📷</span>
                            <span className="text-white text-xs">点击开启</span>
                        </div>
                    )}
                </div>
            )}

            {/* 底部控制区域 */}
            <div className="absolute bottom-0 left-0 right-0 z-20 pb-8">
                {/* 功能按钮行 */}
                <div className="flex items-center justify-center gap-8 mb-6">
                    {/* 麦克风 */}
                    <div className="flex flex-col items-center gap-2">
                        <button
                            onClick={() => isStarted && setIsVoiceChatOn(!isVoiceChatOn)}
                            style={{
                                width: 56,
                                height: 56,
                                borderRadius: '50%',
                                backgroundColor: '#fff',
                                border: 'none',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer',
                                opacity: !isStarted ? 0.5 : 1
                            }}
                        >
                            {isVoiceChatOn ? (
                                <AudioOutlined style={{ fontSize: 22, color: '#000' }} />
                            ) : (
                                <AudioMutedOutlined style={{ fontSize: 22, color: '#000' }} />
                            )}
                        </button>
                        <span className="text-gray-600 text-xs">
                            {isVoiceChatOn ? '麦克风已开' : '麦克风已关'}
                        </span>
                    </div>

                    {/* 扬声器 */}
                    <div className="flex flex-col items-center gap-2">
                        <button
                            onClick={toggleSpeaker}
                            style={{
                                width: 56,
                                height: 56,
                                borderRadius: '50%',
                                backgroundColor: '#fff',
                                border: 'none',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer',
                                opacity: !isStarted ? 0.5 : 1
                            }}
                        >
                            <SoundOutlined style={{ fontSize: 22, color: '#000' }} />
                        </button>
                        <span className="text-gray-600 text-xs">
                            {isSpeakerOn ? '扬声器已开' : '扬声器已关'}
                        </span>
                    </div>

                    {/* 消息 */}
                    <div className="flex flex-col items-center gap-2">
                        <button
                            onClick={() => setIsChatOpen(!isChatOpen)}
                            style={{
                                width: 56,
                                height: 56,
                                borderRadius: '50%',
                                backgroundColor: '#fff',
                                border: 'none',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer'
                            }}
                        >
                            <MessageOutlined style={{ fontSize: 22, color: '#000' }} />
                        </button>
                        <span className="text-gray-600 text-xs">消息</span>
                    </div>

                    {/* 设置 */}
                    <div className="flex flex-col items-center gap-2">
                        <button
                            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
                            style={{
                                width: 56,
                                height: 56,
                                borderRadius: '50%',
                                backgroundColor: '#fff',
                                border: 'none',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer'
                            }}
                        >
                            <SettingOutlined style={{ fontSize: 22, color: '#000' }} />
                        </button>
                        <span className="text-gray-600 text-xs">设置</span>
                    </div>
                </div>

                {/* 挂断/接听按钮 */}
                <div className="flex justify-center">
                    {isStarted ? (
                        <button
                            onClick={stop}
                            style={{
                                width: 64,
                                height: 64,
                                borderRadius: '50%',
                                backgroundColor: '#fa5151',
                                border: 'none',
                                boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer'
                            }}
                        >
                            <PhoneOutlined style={{ fontSize: 28, color: '#fff', transform: 'rotate(135deg)' }} />
                        </button>
                    ) : (
                        <button
                            onClick={start}
                            disabled={isLoading}
                            style={{
                                width: 64,
                                height: 64,
                                borderRadius: '50%',
                                backgroundColor: isLoading ? '#8fdcb8' : '#07c160',
                                border: 'none',
                                boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: isLoading ? 'not-allowed' : 'pointer',
                                opacity: isLoading ? 0.7 : 1,
                                transition: 'all 0.3s ease'
                            }}
                        >
                            {isLoading ? (
                                <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            ) : (
                                <PhoneOutlined style={{ fontSize: 28, color: '#fff', transform: 'rotate(0deg)' }} />
                            )}
                        </button>
                    )}
                </div>
            </div>

            {/* 可收起的聊天侧边栏 */}
            <div
                className={`absolute top-0 right-0 h-full z-30 transition-transform duration-300 ease-in-out ${isChatOpen ? 'translate-x-0' : 'translate-x-full'
                    }`}
            >
                <div className="relative h-full">
                    <button
                        onClick={() => setIsChatOpen(false)}
                        className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 w-6 h-16 bg-white rounded-l-lg flex items-center justify-center shadow-lg"
                    >
                        <LeftOutlined className="text-gray-600" style={{ transform: 'rotate(180deg)' }} />
                    </button>
                    <ChatSidebar
                        chatHistory={chatHistory}
                        onSendMessage={handleSendMessage}
                    />
                </div>
            </div>

            <input type="hidden" id="sessionid" value={sessionId} readOnly />

            {/* 设置面板 */}
            <Settings
                visible={isSettingsOpen}
                onClose={() => setIsSettingsOpen(false)}
            />
        </div>
    );
}
