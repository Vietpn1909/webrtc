import asyncio
import json
import numpy as np
import torch
import logging
import ssl
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import AudioFrame

# Cấu hình logging để dễ debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc")

# === BẢN VÁ LỖI HỆ THỐNG / GIT ===
import df.utils
import subprocess

# Chặn đứng các lời gọi git gây lỗi CreateProcess trên Windows
df.utils.get_commit_hash = lambda *args, **kwargs: "unknown"
df.utils.get_git_root = lambda *args, **kwargs: "unknown"

_orig_popen = subprocess.Popen
def _patched_popen(args, *pargs, **kwargs):
    try:
        return _orig_popen(args, *pargs, **kwargs)
    except (OSError, PermissionError):
        class DummyProcess:
            def __init__(self, args):
                self.args = args
                self.returncode = 0
                self.pid = 9999
                self.stdin = self.stdout = self.stderr = None
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def communicate(self, *a, **k): return (b"", b"")
            def wait(self, *a, **k): return 0
            def poll(self): return 0
            def terminate(self): pass
            def kill(self): pass
        return DummyProcess(args)
subprocess.Popen = _patched_popen
# ===============================

from df.enhance import init_df, enhance

print("Đang nạp mô hình DeepFilterNet3...")
# Nạp model chung nhưng tạo 2 state riêng cho 2 người để tránh nhiễu/treo
df_model, state_user1, _ = init_df()
_, state_user2, _ = init_df()

states = {
    'user1': state_user1,
    'user2': state_user2
}

# Biến lưu trữ track gốc từ WebRTC
room_tracks = {
    'user1': None,
    'user2': None
}

# Bộ đệm toàn cục lưu lại 0.5 giây âm thanh gần nhất của mỗi người
BUFFER_SIZE = 24000 
audio_history = {
    'user1': np.zeros(BUFFER_SIZE, dtype=np.float32),
    'user2': np.zeros(BUFFER_SIZE, dtype=np.float32)
}

def calculate_delay_gcc_phat(mic_sig, ref_sig):
    n = mic_sig.shape[0] + ref_sig.shape[0]
    SIG = np.fft.rfft(mic_sig, n=n)
    REFSIG = np.fft.rfft(ref_sig, n=n)
    R = SIG * np.conj(REFSIG)
    cc = np.fft.irfft(R / (np.abs(R) + 1e-15), n=n)
    max_shift = int(n / 2)
    cc = np.concatenate((cc[-max_shift:], cc[:max_shift+1]))
    shift = np.argmax(np.abs(cc)) - max_shift
    return shift

class AIFilterTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, my_role):
        super().__init__()
        self.my_role = my_role
        self.partner_role = 'user2' if my_role == 'user1' else 'user1'
        self.frame_size = 480  
        self.frame_counter = 0
        self.cached_shift = 0
        self._pts = 0
        self.df_state = states[my_role]

    async def recv(self):
        my_mic_track = room_tracks.get(self.my_role)
        if not my_mic_track:
            await asyncio.sleep(0.01)
            return self._create_silent_frame()

        try:
            my_frame = await my_mic_track.recv()
        except Exception as e:
            logger.warning(f"Lỗi khi nhận frame từ {self.my_role}: {e}")
            return self._create_silent_frame()

        # Chuyển đổi audio sang float32 để xử lý
        my_audio = my_frame.to_ndarray().astype(np.float32) / 32768.0
        
        # Cập nhật lịch sử âm thanh của chính mình (để người kia dùng làm mẫu triệt tiêu vọng)
        audio_history[self.my_role] = np.roll(audio_history[self.my_role], -self.frame_size)
        audio_history[self.my_role][-self.frame_size:] = my_audio[0]

        my_tensor = torch.from_numpy(my_audio)
        partner_track = room_tracks.get(self.partner_role)
        self.frame_counter += 1

        # Chạy xử lý DeepFilterNet trong thread riêng để không làm treo event loop của WebRTC
        clean_tensor = await asyncio.to_thread(self._process_audio, my_tensor, partner_track)

        # Chuyển về định dạng int16 cho WebRTC
        clean_audio = (clean_tensor.squeeze().numpy() * 32768.0).astype(np.int16)
        clean_audio = clean_audio.reshape(1, -1)
        
        new_frame = AudioFrame.from_ndarray(clean_audio, format='s16', layout='mono')
        new_frame.pts = my_frame.pts
        new_frame.sample_rate = my_frame.sample_rate
        new_frame.time_base = my_frame.time_base
        
        return new_frame

    def _process_audio(self, my_tensor, partner_track):
        # Thuật toán triệt tiêu vọng (AEC) sử dụng DeepFilterNet 3
        if partner_track:
            partner_history = audio_history[self.partner_role]
            if np.max(np.abs(partner_history[-4800:])) > 0.01: 
                if self.frame_counter % 50 == 0:
                    my_recent = audio_history[self.my_role][-8000:]
                    partner_recent = partner_history[-8000:]
                    self.cached_shift = calculate_delay_gcc_phat(my_recent, partner_recent)
                
                start_idx = BUFFER_SIZE - self.frame_size + self.cached_shift
                if 0 <= start_idx <= BUFFER_SIZE - self.frame_size:
                    aligned_partner_audio = partner_history[start_idx : start_idx + self.frame_size]
                    partner_tensor = torch.from_numpy(aligned_partner_audio).unsqueeze(0)
                    return enhance(df_model, self.df_state, my_tensor, attn_state=partner_tensor)
        
        return enhance(df_model, self.df_state, my_tensor)

    def _create_silent_frame(self):
        silent_audio = np.zeros((1, 480), dtype=np.int16)
        frame = AudioFrame.from_ndarray(silent_audio, format='s16', layout='mono')
        frame.sample_rate = 48000
        frame.pts = self._pts
        self._pts += 480
        frame.time_base = 1/48000
        return frame

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

async def index(request):
    try:
        content = open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8").read()
        return web.Response(content_type="text/html", text=content)
    except Exception as e:
        return web.Response(status=500, text=str(e))

async def offer(request):
    params = await request.json()
    role = params['role']
    logger.info(f"--> [Server] Nhận yêu cầu kết nối từ: {role}")
    
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()

    # Xác định người kia là ai để lấy âm thanh của họ gửi cho người này
    partner_role = 'user2' if role == 'user1' else 'user1'
    # Tạo track âm thanh (đã lọc AI) để gửi lại cho người đang gọi
    outgoing_track = AIFilterTrack(my_role=partner_role)
    pc.addTrack(outgoing_track)

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            logger.info(f"[{role}] Đã nhận luồng micro từ trình duyệt.")
            room_tracks[role] = track

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"[{role}] Trạng thái kết nối: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed"]:
            room_tracks[role] = None
            await pc.close()

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Đợi thu thập xong các ứng viên ICE (mạng) để trình duyệt không bị treo khi kết nối
    # Điều này cực kỳ quan trọng đối với các trình duyệt Chromium như Cốc Cốc
    import asyncio
    timeout = 5
    while pc.iceGatheringState != "complete" and timeout > 0:
        await asyncio.sleep(0.2)
        timeout -= 0.2

    logger.info(f"<-- [Server] Gửi phản hồi (Answer) tới: {role}")
    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
    )

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    
    # Hỗ trợ HTTPS nếu có chứng chỉ
    ssl_context = None
    cert_path = os.path.join(BASE_DIR, "cert.pem")
    key_path = os.path.join(BASE_DIR, "key.pem")
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(cert_path, key_path)
            logger.info("Đã kích hoạt HTTPS mode")
        except Exception as e:
            logger.warning(f"Lỗi khi nạp SSL: {e}")
            ssl_context = None
    else:
        logger.warning("Không tìm thấy cert.pem/key.pem, chạy ở chế độ HTTP (chỉ localhost mới dùng được micro)")

    logger.info("🚀 Server DeepFilter SFU đang khởi động tại cổng 8080")
    web.run_app(app, port=8080, ssl_context=ssl_context)
