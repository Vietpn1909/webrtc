# AI Walkie-Talkie – DeepFilterNet

Ứng dụng bộ đàm thời gian thực trên web dùng **WebRTC** cho truyền âm thanh hai chiều và **DeepFilterNet** xử lý âm thanh bằng AI. Mục tiêu chính là **khử vọng âm (echo cancellation)** cùng **giảm nhiễu**, tạo trải nghiệm giao tiếp tốt trong chế độ full‑duplex.

Dự án là một prototype/demo cho việc tích hợp xử lý audio bằng AI vào pipeline WebRTC.

---

## 📁 Cấu Trúc Thư Mục
```text
src/
├── index.html       # Frontend WebRTC client
└── server.py        # Backend Python với AI audio processing
```

---

## 🖥️ index.html
Giao diện web đơn giản cho phép hai người dùng (User 1 & User 2) kết nối qua WebRTC.

- Bật microphone và cấu hình `echoCancellation: true` (còn lại tắt noise suppression để nhường cho AI).
- Mỗi tab lựa chọn vai trò và gửi offer/answer tới server.
- Audio đầu vào được phát lại dưới dạng track của đối tác.

Frontend chỉ là **WebRTC client**; mọi xử lý âm thanh diễn ra ở backend.

---

## 🔧 server.py

Backend Python dùng:

- `aiohttp` – HTTP server
- `aiortc` – WebRTC implementation
- `torch` + DeepFilterNet – AI audio processing

### Hàm chính
1. Khởi tạo mô hình DeepFilterNet:
   ```python
   df_model, df_state, _ = init_df()
   ```
2. Lưu track micro của mỗi người vào `room_tracks` khi nhận `on_track`.
3. Tạo `AIFilterTrack` để lọc audio gửi về đối tác.

Pipeline xử lý:
```
Microphone → WebRTC Track → AIFilterTrack (AI) → Clean Audio → Remote Stream
```

---

## 🚀 Cài Đặt & Chạy

### Yêu cầu
- Python 3.8+
- Trình duyệt hỗ trợ WebRTC (Chrome, Firefox, Edge)

### Cài dependencies
```bash
pip install aiohttp aiortc av torch deepfilter
```

### Khởi động server
```bash
python server.py
```
Mở `http://localhost:8080` trên hai tab trình duyệt, chọn User 1/2 rồi bắt đầu nói.

---

## 🪛 Chi tiết Echo Cancellation
Phần quan trọng nhất nằm trong lớp `AIFilterTrack`:

### AIFilterTrack
Kế thừa `MediaStreamTrack` của aiortc, loại âm thanh:
```python
class AIFilterTrack(MediaStreamTrack):
    kind = "audio"
```
- `my_role`/`partner_role`: định vị track micro và track đối tác trong `room_tracks`.
- `recv()` xử lý từng frame audio:
  1. Lấy frame từ micro, chuyển sang `float32` tensor:
     ```python
     my_audio = my_frame.to_ndarray().astype(np.float32) / 32768.0
     my_tensor = torch.from_numpy(my_audio)
     ```
  2. Nếu có frame từ đối tác dùng làm reference, gọi:
     ```python
     clean_tensor = enhance(df_model, df_state, my_tensor, attn_state=partner_tensor)
     ```
     - Chế độ này đồng thời khử vọng âm và giảm nhiễu.
  3. Nếu đối tác im lặng, chỉ dùng `enhance(df_model, df_state, my_tensor)` để giảm nhiễu.
  4. Chuyển tensor trở lại `int16` và đóng gói `AudioFrame` trả về WebRTC.

### Cơ chế hoạt động
- **Attention-based AEC**: đối tác audio được dùng như tín hiệu tham chiếu để mô hình học cách tách vọng âm ra khỏi giọng nói chính.
- Sau khi xử lý xong, audio sạch sẽ được phát lại cho bên kia với độ trễ rất thấp.

### Các lớp xử lý âm thanh (tương ứng trong pipeline)
1. **WebRTC Audio Layer** – nhận track, quản lý frames.
2. **Preprocessing Layer** – chuyển đổi `int16` → `float32` tensor, chuẩn hóa.
3. **AI Echo Cancellation Layer** – DeepFilterNet thực hiện AEC + noise suppression.
4. **Noise Suppression Layer** – khi không có reference, chỉ giảm nhiễu.

Mô hình khởi tạo một lần khi server chạy và giữ trạng thái (`df_state`) cho mỗi frame.

---

## ✅ Ưu điểm & Lưu ý
- Khử vọng âm hiệu quả ngay cả khi cả hai nói cùng lúc.
- Giảm nhiễu môi trường giúp chất lượng rõ ràng.
- Hoạt động realtime, phù hợp giao tiếp song phương.

