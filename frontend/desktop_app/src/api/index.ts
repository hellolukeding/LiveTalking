import client from './client';

export interface OfferPayload {
    sdp: string | undefined;
    type: string | undefined;
    avatar_id: string;
}

export interface OfferResponse {
    sdp: string;
    type: RTCSdpType;
    sessionid: string;
}

export const negotiateOffer = async (payload: OfferPayload): Promise<OfferResponse> => {
    try {
        console.log('[API] Sending WebRTC offer to:', client.defaults.baseURL + '/offer');
        console.log('[API] Offer payload:', { avatar_id: payload.avatar_id, type: payload.type });
        const response = await client.post<OfferResponse>('/offer', payload);
        console.log('[API] WebRTC offer response received:', { status: response.status, hasData: !!response.data });
        return response.data;
    } catch (error: any) {
        console.error('[API] WebRTC offer failed:', {
            message: error.message,
            status: error.response?.status,
            statusText: error.response?.statusText,
            data: error.response?.data,
            url: client.defaults.baseURL + '/offer'
        });
        throw error;
    }
};

export const sendHumanMessage = async (text: string, sessionId: string, interrupt: boolean = true) => {
    return client.post('/human', {
        text,
        type: 'chat',
        interrupt,
        sessionid: parseInt(sessionId),
    });
};

export const isSpeaking = async (sessionId: string) => {
    const response = await client.post('/is_speaking', {
        sessionid: parseInt(sessionId),
    });
    return response.data;
};
