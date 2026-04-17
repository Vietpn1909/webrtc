## Yêu cầu

- Python 3.10+
- Trình duyệt hỗ trợ WebRTC: Chrome, Edge, Firefox (cần cấp quyền microphone)
- Kết nối internet (lần đầu tải model ONNX của Silero VAD từ CDN)

## Cài đặt & chạy

```bash
pip install -r requirements.txt
python src/server.py
```

Mở `http://localhost:8080` trên **2 tab hoặc 2 cửa sổ trình duyệt**. Tab A chọn **User 1**, Tab B chọn **User 2**, rồi bắt đầu nói.

## Cấu hình (tuỳ chọn)

| Biến môi trường | Mặc định | Mô tả |
|-----------------|----------|-------|
| `PORT` | `8080` | Cổng server |
| `FRONTEND_ORIGIN` | `*` | CORS allowed origin |

### Bật HTTPS / WSS

Đặt `cert.pem` và `key.pem` vào thư mục `src/`. Server tự phát hiện và bật HTTPS/WSS.

```bash
# Tạo self-signed cert để test:
openssl req -x509 -newkey rsa:4096 -keyout src/key.pem -out src/cert.pem -days 365 -nodes
```

> **Lưu ý:** WebRTC bắt buộc HTTPS khi deploy ra môi trường production (localhost có thể dùng HTTP).

## Cách hoạt động

1. Trình duyệt xin quyền microphone qua `getUserMedia` với các ràng buộc: Echo Cancellation, Noise Suppression, Auto Gain Control, mono 48kHz.
2. Silero VAD chạy phía client (ONNX Runtime Web) phân tích clone của audio track. Khi phát hiện giọng nói → bật track (gate mở); khi im lặng → tắt track (gate đóng). Debounce: mở sau 180ms, đóng sau 320ms để tránh cắt giữa câu.
3. Python server (`aiohttp`) relay các message `join`, `offer`, `answer`, `candidate` qua WebSocket để 2 trình duyệt thương lượng SDP và trao đổi ICE candidate.
4. Sau khi WebRTC kết nối thành công, âm thanh truyền **thẳng P2P** giữa 2 trình duyệt — server hoàn toàn ra khỏi đường audio.

## Cấu trúc thư mục

```
webrtc/
├── requirements.txt   # aiohttp==3.9.5, aiohttp-cors==0.7.0
├── src/
│   ├── server.py      # Signaling server (Python / aiohttp)
│   └── index.html     # Toàn bộ UI + WebRTC client logic
```
