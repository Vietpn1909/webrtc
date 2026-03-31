# WebRTC AI Audio Hub - Tai lieu du an

## 1) Tong quan

Du an la mot ung dung **dam thoai 2 nguoi theo thoi gian thuc** dung WebRTC, trong do:
- **Client** xu ly echo cancellation/noise suppression/auto gain control ngay tren thiet bi micro.
- **Backend Python** xu ly khu nhieu bang **DeepFilterNet**, sau do tra audio da xu ly ve cho ben con lai.

Muc tieu chinh:
- Tao kenh lien lac audio 2 chieu.
- Giam nhieu/am vang tren luong am thanh.
- Uu tien do tre thap cho call realtime.

## 2) Cau truc thu muc

```text
webrtc/
|- README.md
|- requirements.txt
`- src/
   |- server.py      # Backend signaling + xu ly audio AI
   `- index.html     # Frontend WebRTC 2 nut User1/User2
```

## 3) Cong nghe su dung

- **Backend**: `aiohttp`, `aiortc`, `aiohttp-cors`
- **Audio/AI**: `numpy`, `torch`, `deepfilternet`, `av`
- **Frontend**: HTML + JavaScript thuần (khong framework)
- **Protocol**: WebRTC (SDP offer/answer + ICE/STUN)

## 4) Luong hoat dong

1. Nguoi dung mo trinh duyet, bam `Toi la Nguoi 1` hoac `Toi la Nguoi 2`.
2. Frontend lay micro (`getUserMedia`) voi AEC/NS/AGC va tao `RTCPeerConnection`.
3. Frontend gui SDP offer den backend qua `POST /offer`.
4. Backend tao peer connection, nhan audio track vao.
5. Backend dua audio vao `AIFilterTrack` de:
   - chuan hoa audio,
   - downmix mono,
   - xu ly DeepFilterNet (co fallback passthrough),
   - crossfade/chong clip truoc khi tra ve.
6. Backend tra SDP answer, frontend set remote description va phat audio nhan duoc.

## 5) Cac file quan trong

- `src/server.py`
  - Khoi tao model DeepFilterNet.
  - Xu ly signaling endpoint: `GET /`, `POST /offer`.
  - Quan ly peer connections va stream theo 2 vai tro `user1`, `user2`.
  - Co cac bien tuning latency/chat luong nhu `LOW_LATENCY_MODE`, `AGGRESSIVE_LOW_LATENCY`, `DRY_SIGNAL_RATIO`.
  - Khong thuc hien echo cancellation tham chieu doi phuong o server.

- `src/index.html`
  - Giao dien don gian 2 nut role.
  - Co toggle UI bat/tat `Echo Cancellation`, `Noise Suppression`, `Auto Gain Control`.
  - Tao WebRTC offer/answer voi backend.
  - Thu micro voi constraints uu tien echo cancellation/noise suppression/auto gain control o client.
  - Tu dong chon `BACKEND_URL` theo local/production.

## 6) Yeu cau moi truong

- Python 3.10+ (khuyen nghi dung venv)
- Trinh duyet ho tro WebRTC: Chrome/Edge/Firefox
- May co microphone

Luu y:
- Lan dau chay, viec tai model/dependency co the mat them thoi gian.
- Tren Windows, mot so thu vien audio/video can runtime phu tro (FFmpeg/PyAV da duoc goi qua `av`).

## 7) Cach chay local

### Buoc 1: Tao moi truong ao

```bash
python -m venv .venv
```

Windows (PowerShell):
```bash
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

### Buoc 2: Cai dependencies

```bash
pip install -r requirements.txt
```

### Buoc 3: Chay server

Tu root repo, chay:

```bash
python src/server.py
```

Mac dinh server chay tai `http://localhost:8080`.

### Buoc 4: Thu ket noi

1. Mo 2 tab (hoac 2 trinh duyet) vao `http://localhost:8080`.
2. Tab A bam `Toi la Nguoi 1`, tab B bam `Toi la Nguoi 2`.
3. Cap quyen micro cho ca 2 tab.
4. Kiem tra am thanh da ket noi.

## 8) Bien moi truong huu ich

- `PORT`: cong server (mac dinh `8080`)
- `FRONTEND_ORIGIN`: origin duoc phep CORS cho frontend deploy

Vi du:

```bash
set PORT=8080
set FRONTEND_ORIGIN=https://your-frontend.vercel.app
python src/server.py
```

## 9) HTTPS (tuy chon)

Neu co `cert.pem` va `key.pem` trong `src/`, backend se bat SSL tu dong.

- Co file cert/key -> server co the chay HTTPS.
- Khong co file cert/key -> server chay HTTP binh thuong.

## 10) Su co thuong gap

- **Khong nghe duoc audio**
  - Kiem tra quyen micro tren trinh duyet.
  - Dam bao da mo du 2 role (`user1` va `user2`).
  - Kiem tra log backend xem co loi khi nhan `track` khong.

- **Do tre cao**
  - Kiem tra cac bien latency trong `src/server.py` (`AGGRESSIVE_LOW_LATENCY`, `LOW_LATENCY_MODE`).
  - Tat cac ung dung nang CPU/GPU khi test.

- **Loi CORS khi tach frontend/backend**
  - Dat dung gia tri `FRONTEND_ORIGIN`.
  - Dam bao frontend goi dung `BACKEND_URL`.

## 11) Ghi chu nhanh cho dev moi

- Diem vao chinh de hieu he thong:
  1. `src/index.html` (offer/answer o frontend)
  2. `src/server.py` ham `offer()` (signaling backend)
  3. `AIFilterTrack.recv()` (pipeline xu ly audio)
- Neu can benchmark latency, co the tat xu ly AI bang `ENABLE_AI_PROCESSING = False` de so sanh.
