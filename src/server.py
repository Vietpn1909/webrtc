import asyncio
import json
import numpy as np
import torch
import logging
import ssl
import os
import subprocess
from fractions import Fraction  # Cần thiết để sửa lỗi time_base
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import AudioFrame

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc")

# === BẢN VÁ LỖI HỆ THỐNG / GIT (Dành cho Windows) ===
import df.utils
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

from df.enhance import init_df, enhance

# === KHỞI TẠO MÔ HÌNH VÀ BIẾN TOÀN CỤC ===
print("Đang nạp mô hình DeepFilterNet3...")
df_model, state_user1, _ = init_df()
_, state_user2, _ = init_df()

states = {'user1': state_user1, 'user2': state_user2}
room_tracks = {'user1': None, 'user2': None}
pcs = set()

# === TỐI ƯU HÓA LATENCY ===
# Set ENABLE_AI_PROCESSING = False để test latency baseline (pass-through)
# Set ENABLE_AI_PROCESSING = True để chạy DeepFilterNet (khử nhiễu nhưng có latency cao)
ENABLE_AI_PROCESSING = False

BUFFER_SIZE = 48000 # Tăng buffer lên 1 giây để an toàn hơn với frame size động
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
    return np.argmax(np.abs(cc)) - max_shift

class AIFilterTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, role_to_process):
        super().__init__()
        self.role_to_process = role_to_process
        self.partner_role = 'user2' if role_to_process == 'user1' else 'user1'
        self.frame_counter = 0
        self.cached_shift = 0
        self._pts = 0
        self._logged_audio_meta = False
        self.df_state = states[role_to_process]

    async def recv(self):
        source_track = room_tracks.get(self.role_to_process)
        
        if not source_track:
            await asyncio.sleep(0.02)
            return self._create_silent_frame()

        try:
            frame = await source_track.recv()
        except Exception as e:
            logger.warning(f"Lỗi nhận frame từ {self.role_to_process}: {e}")
            return self._create_silent_frame()

        # 1. Chuyển đổi audio sang float32 với chuẩn hóa đúng theo dtype thực tế.
        audio_ndarray = frame.to_ndarray()
        if not self._logged_audio_meta:
            logger.info(
                f"[{self.role_to_process}] frame format={frame.format.name}, layout={frame.layout.name}, "
                f"shape={audio_ndarray.shape}, dtype={audio_ndarray.dtype}, sample_rate={frame.sample_rate}"
            )
            self._logged_audio_meta = True

        if np.issubdtype(audio_ndarray.dtype, np.integer):
            max_val = float(np.iinfo(audio_ndarray.dtype).max)
            audio_float = audio_ndarray.astype(np.float32) / max_val
        else:
            audio_float = np.clip(audio_ndarray.astype(np.float32), -1.0, 1.0)

        # 2. Downmix về mono ổn định cho cả packed/planar.
        if audio_float.ndim == 1:
            data_to_store = audio_float
        elif audio_float.ndim == 2:
            if audio_float.shape[0] <= 8 and audio_float.shape[1] > audio_float.shape[0]:
                data_to_store = np.mean(audio_float, axis=0)
            else:
                data_to_store = np.mean(audio_float, axis=1)
        else:
            data_to_store = audio_float.reshape(-1)

        data_to_store = np.ascontiguousarray(data_to_store, dtype=np.float32)
            
        current_samples = data_to_store.shape[0]

        # 3. Cập nhật lịch sử (Sửa lỗi Broadcast tại đây)
        # Sử dụng slice động dựa trên chính kích thước của data_to_store
        audio_history[self.role_to_process] = np.roll(audio_history[self.role_to_process], -current_samples)
        audio_history[self.role_to_process][-current_samples:] = data_to_store

        # 4. Chạy AI trong thread riêng
        # Đảm bảo tensor có hình dạng đúng (1, samples)
        my_tensor = torch.from_numpy(data_to_store).unsqueeze(0)
        clean_tensor = await asyncio.to_thread(self._process_audio, my_tensor, current_samples)

        # 5. Trả về frame (Đảm bảo định dạng int16 mono)
        clean_audio_float = clean_tensor.squeeze().detach().cpu().numpy().astype(np.float32)

        # Trộn nhẹ tín hiệu gốc để giảm cảm giác "kim loại" khi khử nhiễu mạnh.
        dry_wet_mix = 0.55
        mixed_audio_float = (1.0 - dry_wet_mix) * clean_audio_float + dry_wet_mix * data_to_store

        # Chống clipping trước khi đổi sang int16 để tránh méo tiếng.
        mixed_audio_float = np.clip(mixed_audio_float, -0.95, 0.95)
        clean_audio_array = (mixed_audio_float * 32768.0).astype(np.int16)
        clean_audio_array = clean_audio_array.reshape(1, -1)
        
        new_frame = AudioFrame.from_ndarray(clean_audio_array, format='s16', layout='mono')
        new_frame.pts = frame.pts
        new_frame.sample_rate = frame.sample_rate
        new_frame.time_base = frame.time_base
        return new_frame
    
    def _process_audio(self, my_tensor, current_samples):
        # Nếu ENABLE_AI_PROCESSING = False, chỉ pass-through không xử lý để test latency.
        if not ENABLE_AI_PROCESSING:
            return my_tensor
        
        self.frame_counter += 1
        partner_track = room_tracks.get(self.partner_role)
        
        if partner_track:
            partner_hist = audio_history[self.partner_role]
            # Kiểm tra nếu đối phương đang nói (AEC)
            if np.max(np.abs(partner_hist[-4800:])) > 0.01:
                if self.frame_counter % 20 == 0: # Cập nhật độ trễ thường xuyên hơn
                    self.cached_shift = calculate_delay_gcc_phat(audio_history[self.role_to_process][-8000:], partner_hist[-8000:])
                
                start_idx = BUFFER_SIZE - current_samples + self.cached_shift
                if 0 <= start_idx <= BUFFER_SIZE - current_samples:
                    ref_audio = partner_hist[start_idx : start_idx + current_samples]
                    # DeepFilterNet enhance() bản hiện tại không hỗ trợ attn_state.
                    # Giữ nhánh AEC để có thể mở rộng sau, nhưng fallback sang enhance chuẩn.
                    _ = ref_audio
                    return enhance(df_model, self.df_state, my_tensor, pad=False, atten_lim_db=8.0)
        
        return enhance(df_model, self.df_state, my_tensor, pad=False, atten_lim_db=8.0)

    def _create_silent_frame(self):
        # Sửa lỗi AttributeError bằng Fraction
        samples = 480
        frame = AudioFrame.from_ndarray(np.zeros((1, samples), dtype=np.int16), format='s16', layout='mono')
        frame.sample_rate = 48000
        frame.pts = self._pts
        frame.time_base = Fraction(1, 48000)
        self._pts += samples
        return frame

# Tạo sẵn các track đầu ra
filtered_outputs = {
    'user1': AIFilterTrack('user1'),
    'user2': AIFilterTrack('user2')
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

async def index(request):
    try:
        content = open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8").read()
        return web.Response(content_type="text/html", text=content)
    except:
        return web.Response(status=404, text="Không tìm thấy index.html")

async def offer(request):
    params = await request.json()
    role = params['role']
    partner_role = 'user2' if role == 'user1' else 'user1'
    
    logger.info(f"--> [Server] {role} kết nối.")
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            logger.info(f"[{role}] Micro stream active.")
            room_tracks[role] = track

    # Gửi track đã qua xử lý của đối phương cho người này
    pc.addTrack(filtered_outputs[partner_role])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"[{role}] Connection: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed"]:
            room_tracks[role] = None
            pcs.discard(pc)

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        if pc.iceConnectionState in ["failed", "closed", "disconnected"]:
            room_tracks[role] = None

    @pc.on("signalingstatechange")
    async def on_signalingstatechange():
        if pc.signalingState == "closed":
            pcs.discard(pc)

    await pc.setRemoteDescription(RTCSessionDescription(sdp=params["sdp"], type=params["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    timeout = 5
    while pc.iceGatheringState != "complete" and timeout > 0:
        await asyncio.sleep(0.1)
        timeout -= 0.1

    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
    )

async def on_shutdown(app):
    # Đóng toàn bộ peer connection trước khi event loop dừng.
    if pcs:
        await asyncio.gather(*[pc.close() for pc in list(pcs)], return_exceptions=True)
    pcs.clear()
    room_tracks['user1'] = None
    room_tracks['user2'] = None

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    
    cert, key = os.path.join(BASE_DIR, "cert.pem"), os.path.join(BASE_DIR, "key.pem")
    ssl_ctx = None
    if os.path.exists(cert) and os.path.exists(key):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert, key)
        logger.info("HTTPS Enabled")
    
    web.run_app(app, port=8080, ssl_context=ssl_ctx)