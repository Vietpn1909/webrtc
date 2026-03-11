import asyncio
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import AudioFrame
import numpy as np
import torch
from df.enhance import init_df, enhance

print("Đang nạp mô hình DeepFilterNet3 vào bộ nhớ...")
df_model, df_state, _ = init_df()

room_tracks = {
    'user1': None,
    'user2': None
}

class AIFilterTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, my_role):
        super().__init__()
        self.my_role = my_role
        self.partner_role = 'user2' if my_role == 'user1' else 'user1'

    async def recv(self):
        my_mic_track = room_tracks.get(self.my_role)
        if not my_mic_track:
            await asyncio.sleep(0.02)
            return self._create_silent_frame()

        my_frame = await my_mic_track.recv()
        
        # Chuyển đổi định dạng cho AI (Tensor Float32)
        my_audio = my_frame.to_ndarray().astype(np.float32) / 32768.0
        my_tensor = torch.from_numpy(my_audio)

        partner_track = room_tracks.get(self.partner_role)
        clean_tensor = None

        if partner_track:
            try:
                # Đợi tối đa 10ms để lấy tiếng của đối tác làm mẫu Khử vọng
                partner_frame = await asyncio.wait_for(partner_track.recv(), timeout=0.01)
                partner_audio = partner_frame.to_ndarray().astype(np.float32) / 32768.0
                partner_tensor = torch.from_numpy(partner_audio)
                
                # Joint AEC & Noise Suppression
                clean_tensor = enhance(df_model, df_state, my_tensor, attn_state=partner_tensor)
            except asyncio.TimeoutError:
                # Đối tác đang im lặng, chỉ cần Khử ồn
                clean_tensor = enhance(df_model, df_state, my_tensor)
        else:
            clean_tensor = enhance(df_model, df_state, my_tensor)

        # Trả lại định dạng WebRTC
        clean_audio = (clean_tensor.squeeze().numpy() * 32768.0).astype(np.int16)
        clean_audio = clean_audio.reshape(1, -1)
        
        new_frame = AudioFrame.from_ndarray(clean_audio, format='s16', layout='mono')
        new_frame.pts = my_frame.pts
        new_frame.sample_rate = my_frame.sample_rate
        new_frame.time_base = my_frame.time_base
        
        return new_frame

    def _create_silent_frame(self):
        silent_audio = np.zeros((1, 480), dtype=np.int16)
        frame = AudioFrame.from_ndarray(silent_audio, format='s16', layout='mono')
        frame.sample_rate = 48000
        frame.time_base = 1/48000
        return frame

async def index(request):
    content = open("index.html", "r", encoding="utf-8").read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    params = await request.json()
    role = params['role']
    
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            print(f"[{role}] Đã nhận luồng micro.")
            room_tracks[role] = track
            
            # Khởi tạo luồng nghe: Lấy micro của ĐỐI TÁC, làm sạch rồi gửi về
            outgoing_track = AIFilterTrack(my_role='user2' if role == 'user1' else 'user1')
            pc.addTrack(outgoing_track)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
    )

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    
    print("🚀 Server DeepFilter SFU đang chạy tại: http://localhost:8080")
    web.run_app(app, port=8080)