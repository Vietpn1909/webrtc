## Cài Đặt & Chạy

### Yêu cầu
- Python 3.10+
- Trình duyệt hỗ trợ WebRTC: Chrome 80+, Edge 80+, Firefox 76+
- Microphone

### Cài dependencies
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Khởi động server
```bash
python src/server.py
```

Mở `http://localhost:8080` trên **hai tab hoặc hai thiết bị** trong cùng mạng LAN, chọn Người 1 / Người 2 rồi cấp quyền microphone.

> Để test giữa PC và mobile trong cùng mạng LAN, truy cập `http://<IP-máy-chạy-server>:8080` trên thiết bị mobile.

---

## Kiến trúc xử lý audio (3 lớp)

Audio pipeline chạy **hoàn toàn ở client**, server không đứng trên đường truyền âm thanh.

```
[Microphone]
     │
     ▼
┌─────────────────────────────────────┐
│ Layer 1 — Browser Native AEC (AEC3) │  echoCancellation: true trong getUserMedia
│  + noiseSuppression + autoGainControl│  Xử lý bởi WebRTC Audio Processing Engine
└─────────────────────────────────────┘
     │ rawStream
     ▼
┌─────────────────────────────────────┐
│ Layer 2 — RNNoise AI Denoising      │  @jitsi/rnnoise-wasm (CDN, ~1MB WASM)
│  ScriptProcessorNode, 480-sample    │  Lọc nhiễu nền còn sót sau Layer 1
│  frames, pre-buffer 20ms            │  Bypass tự động nếu CDN không tải được
└─────────────────────────────────────┘
     │ processedStream
     ▼
┌─────────────────────────────────────┐
│ Layer 3 — VAD Gate                  │  Desktop  → Silero VAD (ONNX Runtime Web)
│  track.enabled = true/false         │  Mobile/iOS → RMS threshold VAD (no model)
│  Clone track riêng cho VAD đọc      │  Fallback tự động nếu Silero load thất bại
└─────────────────────────────────────┘
     │ gated processedStream
     ▼
┌─────────────────────────────────────┐
│ RTCPeerConnection → P2P Audio       │  Signaling qua WebSocket (Python server)
└─────────────────────────────────────┘
```

### Vai trò từng lớp

| Layer | Kỹ thuật | Mục tiêu | Overhead |
|---|---|---|---|
| L1 Native AEC | AEC3 (Chrome/Edge), OS driver | Loại echo loa phản vào mic | ~0 (hardware) |
| L2 RNNoise | LSTM WASM, 480-sample frame | Lọc nhiễu nền còn sót | ~5% CPU |
| L3 VAD Gate | Silero ONNX / RMS threshold | Chặn hoàn toàn khi không nói | ~1-3% CPU |

### Mobile / iOS

- **iOS Safari**: Silero VAD bị bỏ qua (AudioWorklet xung đột AVAudioSession). Layer 3 tự chuyển sang RMS VAD.
- **Android Chrome**: Chạy đầy đủ cả 3 lớp.
- **Thiết bị ≤ 2 CPU core**: Tự động dùng RMS VAD thay Silero để tiết kiệm CPU.

---

## Cách hoạt động (signaling flow)

1. Cả hai tab/thiết bị mở trang → chọn vai Người 1 / Người 2.
2. Frontend build audio pipeline (L1 → L2 → L3).
3. Frontend kết nối WebSocket `/ws` tới Python server, gửi `join`.
4. Khi cả hai đã join, server gửi `peer_ready`.
5. Người 1 tạo SDP offer → gửi qua server → Người 2 tạo SDP answer → trả về.
6. ICE candidate được relay qua server cho đến khi WebRTC hội tụ.
7. Sau khi kết nối: audio đi **thẳng P2P**, server không liên quan đến audio.

---

## Biến môi trường

| Biến | Mặc định | Mô tả |
|---|---|---|
| `PORT` | `8080` | Cổng server |
| `FRONTEND_ORIGIN` | `*` | CORS origin cho production deploy |

Ví dụ:
```bash
PORT=9000 FRONTEND_ORIGIN=https://your-app.vercel.app python src/server.py
```

## HTTPS (tùy chọn)

Đặt `cert.pem` và `key.pem` vào thư mục `src/` — server tự phát hiện và bật SSL.
Mobile thường yêu cầu HTTPS để cấp quyền microphone trên mạng không phải localhost.
