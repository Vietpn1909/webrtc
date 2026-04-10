# WebRTC Audio Hub - Tai lieu du an

## 1) Tong quan

Du an la mot ung dung **dam thoai 2 nguoi theo thoi gian thuc** dung WebRTC. Toan bo xu ly audio chay tren client (trinh duyet), backend Python chi dong vai tro signaling server.

Muc tieu chinh:
- Tao kenh lien lac audio 2 chieu, do tre thap nhat co the.
- Xu ly echo/noise bang 3 lop xep chong, moi lop co the tat/bat doc lap.
- Ho tro ca PC lan mobile (Android va iOS).

## 2) Kien truc xu ly audio (3 lop)

```
Microphone
    |
    v
[L1] Browser Native AEC (AEC3 + NS + AGC)   <- getUserMedia constraints
    |  rawStream
    v
[L2] RNNoise AI Denoising                   <- @jitsi/rnnoise-wasm (WASM, CDN)
    |  processedStream                          ScriptProcessorNode, 480-sample frames
    v
[L3] VAD Gate                               <- Silero VAD (desktop, ONNX Runtime Web)
    |  gated processedStream                    RMS threshold VAD (mobile/iOS fallback)
    v
RTCPeerConnection (P2P audio)
```

### Chi tiet tung lop

**Layer 1 — Native AEC**
- Goi `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })`.
- AEC duoc xu ly boi WebRTC Audio Processing Engine cua browser (AEC3 tren Chrome/Edge).
- Zero overhead, hoat dong tot voi tai nghe/headset.
- Hieu qua giam khi dung loa ngoai.

**Layer 2 — RNNoise**
- Su dung `@jitsi/rnnoise-wasm` tai tu CDN (jsdelivr).
- Xu ly qua `ScriptProcessorNode` (deprecated nhung chay duoc tren moi browser ke ca iOS).
- Buffer logic: ScriptProcessor chunk = 4096 samples; RNNoise frame = 480 samples.
  - `pendingIn`: samples chua du 480.
  - `pendingOut`: samples da xu ly chua copy vao output.
  - 960-sample silence pre-buffer (~20ms) tranh dropout chu ky dau.
- processFrame(frame) chay in-place, range am thanh +-32768.
- Neu CDN load that bai -> bypass hoan toan, stream di thang.

**Layer 3 — VAD Gate**
- "Track Hack": clone track de VAD doc; original track bi `enabled = false` mac dinh.
- Khi VAD phat hien giong noi -> `original.enabled = true` -> WebRTC truyen audio.
- Khi im lang -> `original.enabled = false` -> WebRTC nhan silence.

  *Desktop (hardwareConcurrency > 2, khong phai iOS)*:
  - **Silero VAD**: LSTM model ~1MB, chay qua ONNX Runtime Web.
  - Debounce: speech_start = 180ms, speech_end hold = 320ms.
  - Neu load that bai -> tu dong fallback sang RMS VAD.

  *Mobile/iOS (iOS bat ky, hoac <= 2 CPU core)*:
  - **RMS VAD**: tinh RMS moi animation frame (~60Hz), so nguong `0.012`.
  - Khong can model, zero CDN dependency, universal.
  - Nguong co the chinh trong constant `RMS_THRESHOLD`.

## 3) Cau truc thu muc

```
webrtc/
|- README.md            # Huong dan cai dat & chay
|- PROJECT_OVERVIEW.md  # Tai lieu ky thuat (file nay)
|- requirements.txt     # Python dependencies
`- src/
   |- server.py         # Backend signaling (aiohttp + WebSocket)
   `- index.html        # Frontend - toan bo audio pipeline + WebRTC
```

## 4) Backend (server.py)

- Framework: `aiohttp` + `aiohttp-cors`.
- Quan ly 2 vai tro: `user1`, `user2`.
- Chuyen tiep message: `join` -> `joined`; khi ca 2 join -> `peer_ready`; relay `offer`, `answer`, `candidate`.
- Khong xu ly audio, khong nam tren duong truyen am thanh.
- Ho tro SSL tu dong: neu co `cert.pem` + `key.pem` trong `src/` thi bat HTTPS/WSS.
- Bien moi truong: `PORT` (mac dinh 8080), `FRONTEND_ORIGIN` (CORS).

## 5) Frontend (index.html)

Cac ham quan trong:

| Ham | Lop | Mo ta |
|---|---|---|
| `getLayer1Stream()` | L1 | getUserMedia voi AEC constraints |
| `loadRNNoiseModule()` | L2 | Load @jitsi/rnnoise-wasm tu CDN |
| `buildRNNoisePipeline(stream, mod)` | L2 | Xay ScriptProcessor pipeline |
| `setupVADToggle(stream)` | L3 | Dispatch sang Silero hoac RMS VAD |
| `setupSileroVAD(stream)` | L3 | Silero VAD (desktop) |
| `setupRMSVAD(stream)` | L3 | RMS VAD (mobile fallback) |
| `buildAudioPipeline()` | Tat ca | Orchestrate L1->L2->L3, tra ve gated stream |
| `createPeerConnection()` | WebRTC | RTCPeerConnection + visualizer remote |
| `joinCall(role)` | Main | Goi buildAudioPipeline() roi khoi dong WebRTC |

**isLowEndDevice()**: Tra ve true neu iOS (moi model) hoac hardwareConcurrency <= 2.

## 6) Signaling flow

```
Browser A           Python Server          Browser B
    |                    |                     |
    |-- join(user1) ---> |                     |
    |                    | <-- join(user2) ----|
    |                    |                     |
    | <-- peer_ready --- | --- peer_ready ----> |
    |                    |                     |
    |-- offer(sdp) ----> | --- offer(sdp) ----> |
    |                    |                     |
    | <-- answer(sdp) -- | <-- answer(sdp) ----|
    |                    |                     |
    |-- candidate ----> | --- candidate -----> |
    | <-- candidate ---- | <-- candidate ------|
    |                    |                     |
    |<============= P2P audio (no server) =====>|
```

## 7) Yeu cau moi truong

- Python 3.10+
- Browser: Chrome 80+ / Edge 80+ / Firefox 76+
- Microphone

## 8) Cach chay local

```bash
# Tao moi truong ao
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# Cai dependencies
pip install -r requirements.txt

# Chay server
python src/server.py

# Mo http://localhost:8080 tren 2 tab hoac 2 thiet bi
```

Test PC <-> mobile cung mang LAN:
```bash
# Lay IP may tinh
# Windows: ipconfig | Linux/Mac: ifconfig
python src/server.py
# Mo http://<IP-may-tinh>:8080 tren mobile
```

> Mobile thuong can HTTPS de cap quyen microphone (ngoai localhost).
> Dat cert.pem + key.pem vao src/ de bat SSL, sau do truy cap https://<IP>:8080.

## 9) Su co thuong gap

**Khong nghe duoc audio**
- Kiem tra quyen microphone trong browser.
- Phai mo du 2 role (user1 va user2).

**Layer 2 khong hoat dong (badge "Khong kha dung")**
- CDN jsdelivr co the bi chan trong mang noi bo.
- App van chay duoc, chi L2 bi bypass.

**Silero VAD khong load (fallback sang RMS)**
- Binh thuong tren mang cham. RMS VAD la fallback hop le.
- Tren iOS: luon dung RMS VAD, day la hanh vi co chu y.

**Do tre cao**
- Tat Layer 2 va Layer 3 bang checkbox de so sanh.
- Kiem tra trang thai ICE connection trong browser DevTools.

**Mobile khong cap quyen micro**
- Can HTTPS. Bat SSL bang cach dat cert.pem/key.pem vao src/.
