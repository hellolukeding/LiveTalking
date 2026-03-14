var pc = null;
var sessionId = null;
var destroyUrl = null;

function negotiate() {
    pc.addTransceiver('video', { direction: 'recvonly' });
    pc.addTransceiver('audio', { direction: 'recvonly' });
    return pc.createOffer().then((offer) => {
        return pc.setLocalDescription(offer);
    }).then(() => {
        // wait for ICE gathering to complete, but with a 1500ms timeout
        return new Promise((resolve) => {
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
    }).then(() => {
        var offer = pc.localDescription;
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then((response) => {
        return response.json();
    }).then((answer) => {
        // 保存 sessionid 和 destroy_url
        sessionId = answer.sessionid;
        destroyUrl = answer.destroy_url || null;
        console.log('[Connect] Session created:', sessionId, 'Destroy URL:', destroyUrl);

        document.getElementById('sessionid').value = answer.sessionid
        return pc.setRemoteDescription(answer);
    }).catch((e) => {
        alert(e);
    });
}

function start() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{ urls: ['stun:stun.qq.com:3478'] }];
    }

    pc = new RTCPeerConnection(config);

    // connect audio / video
    pc.addEventListener('track', (evt) => {
        if (evt.track.kind == 'video') {
            document.getElementById('video').srcObject = evt.streams[0];
        } else {
            document.getElementById('audio').srcObject = evt.streams[0];
        }
    });

    document.getElementById('start').style.display = 'none';
    negotiate();
    document.getElementById('stop').style.display = 'inline-block';
}

async function destroySession() {
    """销毁会话"""
    if (!sessionId || !destroyUrl) {
        console.log('[Destroy] No session to destroy');
        return;
    }

    console.log('[Destroy] Destroying session:', sessionId);

    try {
        const response = await fetch(destroyUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (response.ok) {
            console.log('[Destroy] Session destroyed successfully');
        } else {
            console.error('[Destroy] Failed to destroy session, status:', response.status);
        }
    } catch (e) {
        console.error('[Destroy] Error destroying session:', e);
    }

    // 清理变量
    sessionId = null;
    destroyUrl = null;
}

function stop() {
    document.getElementById('stop').style.display = 'none';

    // 先销毁会话，然后关闭连接
    destroySession().finally(() => {
        // close peer connection
        setTimeout(() => {
            pc.close();
            pc = null;
        }, 500);
    });
}

window.onunload = function(event) {
    // 在页面卸载时销毁会话
    destroySession();

    setTimeout(() => {
        if (pc) {
            pc.close();
        }
    }, 500);
};

window.onbeforeunload = function (e) {
    // 在页面即将卸载时销毁会话
    // 使用 sendBeacon 确保请求发送
    if (sessionId && destroyUrl) {
        console.log('[Unload] Sending destroy request via sendBeacon');
        navigator.sendBeacon(destroyUrl, JSON.stringify({}));
        sessionId = null;
        destroyUrl = null;
    }

    setTimeout(() => {
        if (pc) {
            pc.close();
        }
    }, 500);

    e = e || window.event
    // 兼容IE8和Firefox 4之前的版本
    if (e) {
      e.returnValue = '关闭提示'
    }
    // Chrome, Safari, Firefox 4+, Opera 12+ , IE 9+
    return '关闭提示'
}
