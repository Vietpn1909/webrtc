# WebRTC Audio Hub - Tai lieu du an

## 1) Tong quan

Du an la mot ung dung **dam thoai 2 nguoi theo thoi gian thuc** dung WebRTC. Hien tai, he thong duoc toi uu theo huong:
- **Client** xu ly audio ngay tren trinh duyet, gom echo cancellation, noise suppression, auto gain control va VAD gating.
- **Backend Python** chi dong vai tro **signaling server**: trao doi offer/answer/candidate va dong bo trang thai ket noi giua 2 user.

Ly do chuyen xu ly sang client:
- Giam latency ro ret so voi viec dua audio ve server roi xu ly.
- WebRTC co san cac co che xu ly micro tren trinh duyet.
- Giu duong audio theo kieu P2P, backend khong nam tren duong truyen am thanh.

Muc tieu chinh:
- Tao kenh lien lac audio 2 chieu.
- Giam delay toi da cho call realtime.
- Giu backend don gian, chi phuc vu signaling va ket noi.

## 2) Cau truc thu muc

```text
webrtc/
|- README.md
|- requirements.txt
`- src/
  |- server.py      # Backend signaling
  `- index.html     # Frontend WebRTC 2 nut User1/User2
```

## 3) Cong nghe su dung

- **Backend**: `aiohttp`, `aiohttp-cors`
- **Frontend**: HTML + JavaScript thuần (khong framework)
- **Audio tren client**: `getUserMedia`, Web Audio API, VAD trong browser
- **Protocol**: WebRTC (SDP offer/answer + ICE/STUN) + WebSocket signaling

## 4) Luong hoat dong

1. Nguoi dung mo trinh duyet, bam `Toi la Nguoi 1` hoac `Toi la Nguoi 2`.
2. Frontend lay micro (`getUserMedia`) voi AEC/NS/AGC va tao `RTCPeerConnection`.
3. Frontend ket noi toi backend qua WebSocket `/ws` de xin join vao vai tro dang chon.
4. Backend luu trang thai 2 user, khi ca 2 ben da san sang se gui tin hieu `peer_ready`.
5. User 1 tao SDP offer, gui qua backend sang user 2; user 2 tao SDP answer va tra lai.
6. ICE candidate tiep tuc duoc chuyen qua backend de WebRTC hoi tu.
7. Khi ket noi xong, audio di truc tiep P2P giua 2 trinh duyet.
8. Client su dung VAD de bat/tat track micro, giup giam am vong va tap am khi khong co tieng noi.

## 5) Cac file quan trong

- `src/server.py`
  - Chay backend signaling bang `aiohttp`.
  - Quan ly ket noi WebSocket cho 2 vai tro `user1`, `user2`.
  - Chuyen tiep `join`, `offer`, `answer`, `candidate` giua 2 ben.
  - Khong xu ly audio, khong nam trong duong truyen am thanh.

- `src/index.html`
  - Giao dien don gian 2 nut role.
  - Lay micro va bat cac tro ly audio cua trinh duyet.
  - Tao WebRTC offer/answer voi backend qua WebSocket.
  - Chay VAD de gate track micro, dam bao call realtime it vang va it latency.
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
  - Kiem tra network, firewall va trang thai WebRTC/ICE.
  - Dam bao audio xu ly o client dang duoc bat dung cach.
  - Tat cac ung dung nang CPU/GPU khi test.

- **Loi CORS khi tach frontend/backend**
  - Dat dung gia tri `FRONTEND_ORIGIN`.
  - Dam bao frontend goi dung `BACKEND_URL`.

## 11) Ghi chu nhanh cho dev moi

- Diem vao chinh de hieu he thong:
  1. `src/index.html` (xin micro, VAD, offer/answer, phat audio)
  2. `src/server.py` (signaling backend)
  3. Luong audio thuc te chay trong browser, khong di qua server.
- Neu can benchmark latency, hay so sanh giua bat/tat VAD va cac thuoc tinh audio cua trinh duyet.
