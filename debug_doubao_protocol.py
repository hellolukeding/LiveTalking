import asyncio
import os
import websocket
import uuid
import time
import json
import gzip
from dotenv import load_dotenv

load_dotenv()

appid = os.getenv("DOUBAO_APPID")
token = os.getenv("DOUBAO_ACCESS_TOKEN") or os.getenv("DOUBAO_AccessKeyID") or os.getenv("DOUBAO_TOKEN")
voice_id = os.getenv("DOUBAO_VOICE_ID")
resource_id = os.getenv("DOUBAO_RESOURCE_ID")

api_url = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"

header = [
    f"X-Api-App-Key: {appid}",
    f"X-Api-Access-Key: {token}",
    f"X-Api-Resource-Id: {resource_id}",
    f"X-Api-Connect-Id: {str(uuid.uuid4())}",
]

ws = websocket.create_connection(api_url, timeout=10, header=header)

request_json = {
    "user": {"uid": str(uuid.uuid4())},
    "req_params": {
        "speaker": voice_id,
        "audio_params": {"format": "pcm", "sample_rate": 16000, "enable_timestamp": False},
        "text": "测试一下",
    },
}

header_req = bytearray(b'\x11\x10\x11\x00')
payload_bytes = json.dumps(request_json).encode('utf-8')
payload_bytes = gzip.compress(payload_bytes)

full_request = bytearray(header_req)
full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
full_request.extend(payload_bytes)

ws.send_binary(bytes(full_request))

for _ in range(5):
    result = ws.recv()
    print(f"Received frame of length: {len(result)}")
    if len(result) > 0:
        header_size = (result[0] & 0x0F) * 4
        message_type = (result[1] & 0xF0) >> 4
        compression = result[1] & 0x0F
        print(f"Header size: {header_size}, Type: {message_type}, compression: {compression}")
        payload = result[header_size:]
        print(f"Payload length: {len(payload)}")
        print(f"First 32 bytes of payload hex: {payload[:32].hex()}")
        
        if message_type == 0xb: # audio
            # let's decode seq and size
            if len(payload) >= 8:
                seq = int.from_bytes(payload[:4], "big")
                size = int.from_bytes(payload[4:8], "big")
                print(f"Audio payload parsed seq={seq}, size={size}")

ws.close()
