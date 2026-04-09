## Cài Đặt & Chạy

### Yêu cầu
- Python 3.10
- Trình duyệt hỗ trợ WebRTC (Chrome, Firefox, Edge)

### Cài dependencies
```bash
pip install -r requirements.txt
```

### Khởi động server
```bash
python src/server.py
```
Mở `http://localhost:8080` trên hai tab trình duyệt, chọn User 1/2 rồi bắt đầu nói.

## Cách hoạt động

- Trình duyệt xin micro bằng `getUserMedia` và bật các cơ chế xử lý sẵn có của browser như echo cancellation, noise suppression, auto gain control.
- Browser tạo `RTCPeerConnection` để truyền audio theo kiểu P2P.
- Python server chỉ làm nhiệm vụ signaling qua WebSocket, tức là chuyển tiếp `join`, `offer`, `answer`, `candidate` giữa 2 người.
- Phần kiểm soát tiếng nói hiện chạy ở client bằng VAD, nên server không còn xử lý hay lọc audio nữa.

Nói ngắn gọn khi demo: backend không đứng trên đường audio, backend chỉ giúp 2 trình duyệt bắt tay với nhau; âm thanh đi thẳng giữa 2 máy để giảm latency.

---




