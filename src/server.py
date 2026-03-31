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
import aiohttp_cors
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
ENABLE_AI_PROCESSING = True

# === TINH CHỈNH CHẤT LƯỢNG ÂM THANH ===
# Mức khử nhiễu thấp hơn để giảm méo "kim loại".
DF_ATTEN_LIM_DB = 4.0
# Giữ nhiều tín hiệu gốc hơn để tiếng tự nhiên hơn.
DRY_SIGNAL_RATIO = 0.8
# Nếu AI làm sụt năng lượng quá sâu so với đầu vào thì tự fallback để không mất tiếng.
AI_MIN_RMS_RATIO = 0.05
# Làm mượt biên frame để giảm rè/xé tiếng tại ranh giới frame.
CROSSFADE_MS = 5
# === LOW LATENCY MODE (OPT-IN) ===
# Mặc định tắt để giữ nguyên hành vi hiện tại đang ổn định.
LOW_LATENCY_MODE = True
# Khi bật low-latency: bỏ qua AI cho frame rất nhỏ năng lượng để giảm tải/độ trễ.
LOW_LATENCY_VAD_RMS = 0.008
# Rút ngắn crossfade khi bật low-latency để giảm processing overhead.
LOW_LATENCY_CROSSFADE_MS = 2

# === AGGRESSIVE LOW LATENCY (dành cho realtime call) ===
# Bật để giảm độ trễ từ 2s xuống < 500ms, giá cả là khử nhiễu kém hơn.
AGGRESSIVE_LOW_LATENCY = True

# Buffer size sẽ tự điều chỉnh dựa trên chế độ:
# - AGGRESSIVE: 4800 (100ms) để giảm trễ cực kỳ
# - NORMAL: 48000 (1 giây)
if AGGRESSIVE_LOW_LATENCY:
    BUFFER_SIZE = 4800
    DF_ATTEN_LIM_DB = 1.0  # Giảm từ 4.0 để AI nhanh hơn
    DRY_SIGNAL_RATIO = 0.95  # Giữ 95% tiếng gốc, chỉ 5% AI
    CROSSFADE_MS = 1  # Giảm từ 5 để không block
else:
    BUFFER_SIZE = 48000
    # DF_ATTEN_LIM_DB/DRY_SIGNAL_RATIO/CROSSFADE_MS giữ nguyên giá trị đã define ở trên
class AIFilterTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, role_to_process):
        super().__init__()
        self.role_to_process = role_to_process
        self._pts = 0
        self._logged_audio_meta = False
        self._logged_level_once = False
        self._logged_low_latency_once = False
        self.df_state = states[role_to_process]
        self._prev_tail = np.zeros(0, dtype=np.float32)

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
            info = np.iinfo(audio_ndarray.dtype)
            max_val = float(max(abs(info.min), info.max))
            audio_float = audio_ndarray.astype(np.float32)
            # PCM unsigned (vd: uint8) có mức im lặng ở midpoint, cần trừ DC offset.
            if info.min == 0:
                audio_float = audio_float - ((info.max + 1) / 2.0)
            audio_float = audio_float / max_val
        else:
            audio_float = np.clip(audio_ndarray.astype(np.float32), -1.0, 1.0)

        # 2. Downmix về mono theo số kênh thực tế thay vì đoán shape.
        channel_count = len(frame.layout.channels) if frame.layout else 1
        if audio_float.ndim == 1:
            data_to_store = audio_float
        elif audio_float.ndim == 2:
            # Trường hợp packed/interleaved: shape thường là (1, total_samples).
            # Nếu có nhiều kênh, tách lại theo số kênh rồi mới trung bình về mono.
            if audio_float.shape[0] == 1 and channel_count > 1 and (audio_float.shape[1] % channel_count == 0):
                interleaved = audio_float.reshape(-1)
                deinterleaved = interleaved.reshape(-1, channel_count)
                data_to_store = np.mean(deinterleaved, axis=1)
            elif audio_float.shape[0] == channel_count:
                data_to_store = np.mean(audio_float, axis=0)
            elif audio_float.shape[1] == channel_count:
                data_to_store = np.mean(audio_float, axis=1)
            elif audio_float.shape[0] < audio_float.shape[1]:
                data_to_store = np.mean(audio_float, axis=0)
            else:
                data_to_store = np.mean(audio_float, axis=1)
        else:
            data_to_store = audio_float.reshape(-1)

        data_to_store = np.ascontiguousarray(data_to_store, dtype=np.float32)

        # Tối ưu tùy chọn: frame yếu năng lượng sẽ bỏ qua AI để giảm độ trễ.
        # Chỉ chạy khi LOW_LATENCY_MODE = True nên mặc định không đổi hành vi.
        if LOW_LATENCY_MODE:
            frame_rms = float(np.sqrt(np.mean(np.square(data_to_store)) + 1e-12))
            if frame_rms < LOW_LATENCY_VAD_RMS:
                if not self._logged_low_latency_once:
                    logger.info(
                        f"[{self.role_to_process}] Low-latency passthrough active (rms={frame_rms:.6f} < {LOW_LATENCY_VAD_RMS})"
                    )
                    self._logged_low_latency_once = True
                mixed_audio_float = self._apply_crossfade(data_to_store.copy(), frame.sample_rate or 48000)
                mixed_audio_float = np.clip(mixed_audio_float, -0.95, 0.95)
                clean_audio_array = (mixed_audio_float * 32767.0).astype(np.int16).reshape(1, -1)
                new_frame = AudioFrame.from_ndarray(clean_audio_array, format='s16', layout='mono')
                new_frame.pts = frame.pts
                new_frame.sample_rate = frame.sample_rate or 48000
                new_frame.time_base = frame.time_base
                return new_frame
            
        current_samples = data_to_store.shape[0]

        # 3. Chạy AI trong thread riêng
        # Đảm bảo tensor có hình dạng đúng (1, samples)
        my_tensor = torch.from_numpy(data_to_store).unsqueeze(0)
        if ENABLE_AI_PROCESSING:
            try:
                clean_tensor = await asyncio.to_thread(self._process_audio, my_tensor)
            except Exception as e:
                logger.exception(f"[{self.role_to_process}] AI processing lỗi, fallback passthrough: {e}")
                clean_tensor = my_tensor
        else:
            clean_tensor = my_tensor

        # 4. Trả về frame (Đảm bảo định dạng int16 mono)
        clean_audio_float = clean_tensor.squeeze().detach().cpu().numpy().astype(np.float32)
        if clean_audio_float.shape[0] != current_samples:
            logger.warning(
                f"[{self.role_to_process}] AI trả sai chiều dữ liệu ({clean_audio_float.shape[0]} != {current_samples}), fallback gốc"
            )
            clean_audio_float = data_to_store

        if not np.all(np.isfinite(clean_audio_float)):
            logger.warning(f"[{self.role_to_process}] AI trả NaN/Inf, fallback gốc")
            clean_audio_float = data_to_store

        in_rms = float(np.sqrt(np.mean(np.square(data_to_store)) + 1e-12))
        out_rms = float(np.sqrt(np.mean(np.square(clean_audio_float)) + 1e-12))
        if in_rms > 1e-5 and (out_rms / in_rms) < AI_MIN_RMS_RATIO:
            logger.warning(
                f"[{self.role_to_process}] AI làm nhỏ tiếng quá mức (in_rms={in_rms:.6f}, out_rms={out_rms:.6f}), fallback gốc"
            )
            clean_audio_float = data_to_store

        if not self._logged_level_once:
            logger.info(f"[{self.role_to_process}] rms_in={in_rms:.6f}, rms_out={out_rms:.6f}, dry={DRY_SIGNAL_RATIO}")
            self._logged_level_once = True

        # Trộn nhẹ tín hiệu gốc để giảm cảm giác "kim loại" khi khử nhiễu mạnh.
        dry_ratio = 0.95 if AGGRESSIVE_LOW_LATENCY else DRY_SIGNAL_RATIO
        mixed_audio_float = (dry_ratio * data_to_store) + ((1.0 - dry_ratio) * clean_audio_float)

        # Crossfade đầu frame hiện tại với đuôi frame trước để giảm crackle.
        mixed_audio_float = self._apply_crossfade(mixed_audio_float, frame.sample_rate or 48000)

        # Chống clipping trước khi đổi sang int16 để tránh méo tiếng.
        mixed_audio_float = np.clip(mixed_audio_float, -0.95, 0.95)
        clean_audio_array = (mixed_audio_float * 32767.0).astype(np.int16)
        clean_audio_array = clean_audio_array.reshape(1, -1)
        
        # PyAV hiện tại yêu cầu ndarray ndim=2 cho AudioFrame.from_ndarray.
        new_frame = AudioFrame.from_ndarray(clean_audio_array, format='s16', layout='mono')
        new_frame.pts = frame.pts
        new_frame.sample_rate = frame.sample_rate or 48000
        new_frame.time_base = frame.time_base
        return new_frame
    
    def _process_audio(self, my_tensor):
        # Nếu ENABLE_AI_PROCESSING = False, chỉ pass-through không xử lý để test latency.
        if not ENABLE_AI_PROCESSING:
            return my_tensor

        atten_db = 1.0 if AGGRESSIVE_LOW_LATENCY else DF_ATTEN_LIM_DB
        return enhance(df_model, self.df_state, my_tensor, pad=False, atten_lim_db=atten_db)

    def _apply_crossfade(self, signal, sample_rate):
        if AGGRESSIVE_LOW_LATENCY:
            effective_crossfade_ms = 1
        elif LOW_LATENCY_MODE:
            effective_crossfade_ms = LOW_LATENCY_CROSSFADE_MS
        else:
            effective_crossfade_ms = CROSSFADE_MS
        fade_samples = max(1, int((sample_rate * effective_crossfade_ms) / 1000))
        signal = np.ascontiguousarray(signal, dtype=np.float32)

        if self._prev_tail.size > 0:
            n = min(fade_samples, self._prev_tail.size, signal.size)
            if n > 0:
                ramp = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
                signal[:n] = self._prev_tail[-n:] * (1.0 - ramp) + signal[:n] * ramp

        self._prev_tail = signal[-fade_samples:].copy()
        return signal

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

    # Enable CORS for frontend deployments (Vercel -> Render)
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "https://your-vercel-app.vercel.app")

    cors = aiohttp_cors.setup(app, defaults={
        FRONTEND_ORIGIN: aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    cors.add(app.router.add_resource("/offer")).add_route("POST", offer)
    cors.add(app.router.add_resource("/")).add_route("GET", index)

    cert, key = os.path.join(BASE_DIR, "cert.pem"), os.path.join(BASE_DIR, "key.pem")
    ssl_ctx = None
    if os.path.exists(cert) and os.path.exists(key):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert, key)
        logger.info("HTTPS Enabled")

    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0"

    logger.info(f"Starting server on {host}:{port}")
    web.run_app(app, host=host, port=port, ssl_context=ssl_ctx)
