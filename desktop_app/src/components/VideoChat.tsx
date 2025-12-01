import { PlayCircleOutlined, PoweroffOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { negotiateOffer } from '../api';

export default function VideoChat() {
    const [sessionId, setSessionId] = useState<string>('0');
    const [isStarted, setIsStarted] = useState(false);
    const videoRef = useRef<HTMLVideoElement>(null);
    const audioRef = useRef<HTMLAudioElement>(null);
    const pcRef = useRef<RTCPeerConnection | null>(null);

    const start = async () => {
        if (isStarted) return;

        const config: RTCConfiguration = {
            sdpSemantics: 'unified-plan'
        } as any;

        const pc = new RTCPeerConnection(config);
        pcRef.current = pc;

        pc.addEventListener('track', (evt) => {
            if (evt.track.kind === 'video') {
                if (videoRef.current) videoRef.current.srcObject = evt.streams[0];
            } else {
                if (audioRef.current) audioRef.current.srcObject = evt.streams[0];
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

    useEffect(() => {
        // Auto start on mount
        start();
        return () => {
            stop();
        }
    }, []);

    return (
        <div className="relative w-full h-full bg-black overflow-hidden">
            {/* Video Area */}
            <video
                ref={videoRef}
                autoPlay
                playsInline
                className="w-full h-full object-contain"
            />
            <audio ref={audioRef} autoPlay />

            {/* Controls Overlay */}
            <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 z-10">
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
            </div>

            {/* Hidden input for ASR iframe to read sessionid */}
            <input type="hidden" id="sessionid" value={sessionId} readOnly />

            {/* Hidden ASR iframe for voice processing */}
            <iframe
                src="/asr/index.html"
                className="hidden"
                title="ASR Interface"
                style={{ display: 'none' }}
            />
        </div>
    );
}