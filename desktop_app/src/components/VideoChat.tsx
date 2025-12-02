import { PlayCircleOutlined, PoweroffOutlined } from '@ant-design/icons';
import { Button, message, Switch } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { negotiateOffer, sendHumanMessage } from '../api';
import ChatSidebar, { ChatMessage } from './ChatSidebar';

export default function VideoChat() {
    const [sessionId, setSessionId] = useState<string>('0');
    const [isStarted, setIsStarted] = useState(false);
    const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);

    const videoRef = useRef<HTMLVideoElement>(null);
    const audioRef = useRef<HTMLAudioElement>(null);
    const pcRef = useRef<RTCPeerConnection | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const [isVoiceChatOn, setIsVoiceChatOn] = useState(false);
    const recognitionRef = useRef<any>(null);

    useEffect(() => {
        if (isVoiceChatOn && isStarted) {
            const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
            if (!SpeechRecognition) {
                message.error('您的浏览器不支持语音识别');
                setIsVoiceChatOn(false);
                return;
            }
            const recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = false;
            recognition.lang = 'zh-CN';

            recognition.onresult = (event: any) => {
                const last = event.results.length - 1;
                const text = event.results[last][0].transcript;
                if (text && text.trim()) {
                    handleSendMessage(text.trim());
                }
            };

            recognition.onerror = (event: any) => {
                console.error('Speech recognition error', event.error);
            };

            recognition.onend = () => {
                // Check ref to ensure we still want to be running
                if (isVoiceChatOn && isStarted && recognitionRef.current) {
                    try {
                        recognition.start();
                    } catch (e) {
                        console.error('Failed to restart recognition', e);
                    }
                }
            };

            try {
                recognition.start();
                recognitionRef.current = recognition;
                message.success('语音识别已开启');
            } catch (e) {
                console.error(e);
                message.error('无法开启语音识别');
                setIsVoiceChatOn(false);
            }
        } else {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
                recognitionRef.current = null;
            }
        }

        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
                recognitionRef.current = null;
            }
        };
    }, [isVoiceChatOn, isStarted]);

    const resetTimer = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (isStarted) {
            timerRef.current = setTimeout(() => {
                message.info('长时间未操作，已自动断开连接');
                stop();
            }, 60000);
        }
    };

    const start = async () => {
        if (isStarted) return;

        const config: RTCConfiguration = {
            sdpSemantics: 'unified-plan'
        } as any;

        const pc = new RTCPeerConnection(config);
        pcRef.current = pc;

        const dc = pc.createDataChannel("chat");
        dc.onmessage = (event) => {
            const text = event.data;
            if (text) {
                setChatHistory(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                        return [
                            ...prev.slice(0, -1),
                            { ...lastMsg, content: lastMsg.content + text }
                        ];
                    } else {
                        return [...prev, {
                            role: 'assistant',
                            content: text,
                            timestamp: Date.now()
                        }];
                    }
                });
            }
        };

        pc.addEventListener('iceconnectionstatechange', () => {
            console.log('ICE Connection State:', pc.iceConnectionState);
        });

        pc.addEventListener('icegatheringstatechange', () => {
            console.log('ICE Gathering State:', pc.iceGatheringState);
        });

        pc.addEventListener('signalingstatechange', () => {
            console.log('Signaling State:', pc.signalingState);
        });

        pc.addEventListener('track', (evt) => {
            console.log('Track received:', evt.track.kind);
            if (evt.track.kind === 'video') {
                if (videoRef.current) {
                    console.log('Setting video srcObject');
                    videoRef.current.srcObject = evt.streams[0];
                }
            } else {
                if (audioRef.current) {
                    console.log('Setting audio srcObject');
                    audioRef.current.srcObject = evt.streams[0];
                }
            }
        });

        pc.addTransceiver('video', { direction: 'recvonly' });
        pc.addTransceiver('audio', { direction: 'recvonly' });

        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);

            await new Promise<void>((resolve) => {
                if (pc.iceGatheringState === 'complete') {
                    resolve();
                } else {
                    const checkState = () => {
                        if (pc.iceGatheringState === 'complete') {
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
            });

            setSessionId(answer.sessionid);
            await pc.setRemoteDescription(answer);
            setIsStarted(true);
            message.success('连接成功');

        } catch (e) {
            console.error(e);
            message.error('连接失败: ' + e);
        }
    };

    const stop = () => {
        if (pcRef.current) {
            pcRef.current.close();
            pcRef.current = null;
        }
        setIsStarted(false);
        message.info('已断开连接');
    };

    const handleSendMessage = async (text: string) => {
        resetTimer();
        // Add to chat history
        setChatHistory(prev => [...prev, {
            role: 'user',
            content: text,
            timestamp: Date.now()
        }]);

        try {
            await sendHumanMessage(text, sessionId);
        } catch (e) {
            console.error(e);
            message.error('发送失败');
        }
    };

    useEffect(() => {
        resetTimer();
        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [isStarted]);

    useEffect(() => {
        return () => {
            stop();
        }
    }, []);

    return (
        <div
            className="flex w-full h-full bg-black overflow-hidden"
            onMouseMove={resetTimer}
            onClick={resetTimer}
        >
            {/* Video Area */}
            <div className="flex-1 relative">
                {!isStarted && (
                    <div className="absolute inset-0 flex items-center justify-center z-20 text-white bg-gray-900">
                        <div className="text-center">
                            <div className="text-2xl mb-4 font-light">等待连接</div>
                            <div className="text-gray-400">请点击下方按钮开始连接</div>
                        </div>
                    </div>
                )}
                <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    className="w-full h-full object-contain"
                    onLoadedMetadata={() => console.log('Video loaded metadata')}
                    onPlaying={() => console.log('Video playing')}
                    onWaiting={() => console.log('Video waiting')}
                    onError={(e) => console.error('Video error', e)}
                />
                <audio ref={audioRef} autoPlay />

                {/* Controls Overlay */}
                <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 z-30 flex items-center gap-4 bg-gray-900/60 p-4 rounded-2xl backdrop-blur-md border border-white/10">
                    <Button
                        type={isStarted ? "primary" : "default"}
                        danger={isStarted}
                        shape="round"
                        size="large"
                        icon={isStarted ? <PoweroffOutlined /> : <PlayCircleOutlined />}
                        onClick={isStarted ? stop : start}
                        className="shadow-lg"
                    >
                        {isStarted ? '断开连接' : '开始连接'}
                    </Button>
                    <div className="flex items-center gap-2 text-white border-l border-white/20 pl-4">
                        <span className="text-sm font-medium">语音对话</span>
                        <Switch
                            checked={isVoiceChatOn}
                            onChange={setIsVoiceChatOn}
                            className="bg-gray-600"
                        />
                    </div>
                </div>
            </div>

            {/* Chat Sidebar */}
            <ChatSidebar
                chatHistory={chatHistory}
                onSendMessage={handleSendMessage}
            />

            {/* Hidden input for ASR iframe to read sessionid */}
            <input type="hidden" id="sessionid" value={sessionId} readOnly />
        </div>
    );
}