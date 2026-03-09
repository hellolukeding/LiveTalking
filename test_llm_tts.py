import asyncio
import json
import logging
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription

async def run_test():
    pc = RTCPeerConnection()
    pc.addTransceiver("video", direction="recvonly")
    pc.addTransceiver("audio", direction="recvonly")
    
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    
    # Wait for the tracks to be added by the server
    @pc.on("track")
    def on_track(track):
        print(f"Receiving {track.kind}")
        async def consume():
            try:
                frame = await track.recv()
                print(f"Got {track.kind} frame!")
            except Exception as e:
                pass
        asyncio.ensure_future(consume())
    
    # 1. /offer
    payload = {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }
    
    async with aiohttp.ClientSession() as session:
        print("Sending /offer...")
        async with session.post('http://127.0.0.1:8010/offer', json=payload) as resp:
            data = await resp.json()
            sessionid = data.get('sessionid')
            print(f"Got sessionid: {sessionid}")
            
            # Apply the server's answer to start the connection
            from aiortc import RTCSessionDescription
            answer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
            await pc.setRemoteDescription(answer)
            
            # Wait for WebRTC to establish
            await asyncio.sleep(2)
            
            # 2. /human to trigger LLM and TTS
            human_payload = {
                "sessionid": sessionid,
                "type": "chat",
                "text": "你好啊，很高兴认识你！"
            }
            print("Sending /human to trigger LLM and TTS...")
            async with session.post('http://127.0.0.1:8010/human', json=human_payload) as human_resp:
                human_data = await human_resp.json()
                print(f"/human response: {human_data}")
                
            # Wait a bit to let it process TTS
            await asyncio.sleep(15)

asyncio.run(run_test())
