# 🚀 AI Audio Hub - Deployment Guide

Hệ thống bộ đàm khử vọng sử dụng DeepFilterNet 3 với WebRTC, deploy trên Vercel (frontend) và Render (backend).

## 📋 Tổng quan

- **Frontend**: HTML/CSS/JS static, deploy trên Vercel
- **Backend**: Python WebRTC server với AI khử nhiễu, deploy trên Render
- **Công nghệ**: WebRTC, DeepFilterNet, aiohttp, aiortc

## 🛠️ Yêu cầu hệ thống

### Backend (Render)
- Python 3.8+
- CPU/GPU đủ mạnh cho DeepFilterNet (khuyến nghị GPU)
- RAM: tối thiểu 2GB, khuyến nghị 4GB+
- Disk: 1GB+ cho model DeepFilterNet

### Frontend (Vercel)
- Static hosting
- HTTPS tự động

## 📦 Chuẩn bị

### 1. Clone repository
```bash
git clone <your-repo-url>
cd webrtc
```

### 2. Cài đặt dependencies local
```bash
pip install -r requirements.txt
```

### 3. Test local
```bash
# Terminal 1: Backend
python src/server.py

# Terminal 2: Frontend
cd src
python -m http.server 3000
# Truy cập http://localhost:3000
```

## � Deploy với Docker

### Yêu cầu
- Docker và Docker Compose
- Docker Desktop (cho GPU support nếu cần)

### 1. Chuẩn bị environment
```bash
cp .env.example .env
# Edit .env với cấu hình của bạn
```

### 2. Build và chạy
```bash
# Quick start với script (Linux/Mac)
./deploy.sh

# Windows PowerShell:
# .\deploy.sh

# Hoặc dùng Make (Linux/Mac):
make dev

# Hoặc manual commands:
docker-compose up --build
```

### 3. Truy cập
- Frontend: http://localhost
- Backend: http://localhost:8080
- Health check: http://localhost/health

### 3. Truy cập
- Frontend: http://localhost
- Backend: http://localhost:8080
- Health check: http://localhost/health

### 3. Truy cập
- Frontend: http://localhost
- Backend: http://localhost:8080
- Health check: http://localhost/health

### 3. Truy cập
- Frontend: http://localhost
- Backend: http://localhost:8080
- Health check: http://localhost/health

### 4. Logs và debug
```bash
# View logs
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# Stop services
docker-compose down

# Rebuild sau khi thay đổi code
docker-compose up --build --force-recreate
```

### 5. Production deployment
```bash
# Với custom domain
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale backend (nếu cần multiple instances)
docker-compose up -d --scale backend=2
```

### 6. GPU Support (tùy chọn)
Để enable GPU cho DeepFilterNet:
```yaml
# Thêm vào docker-compose.yml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## �🚀 Deploy Backend (Render)

### 1. Tạo tài khoản Render
- Đăng ký tại [render.com](https://render.com)
- Kết nối GitHub repository

### 2. Tạo Web Service
- **Service Type**: Web Service
- **Runtime**: Python 3
- **Build Command**:
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**:
  ```bash
  python src/server.py
  ```

### 3. Cấu hình Environment Variables
Trong Settings > Environment:

| Variable | Value | Mô tả |
|----------|-------|-------|
| `PORT` | (auto) | Port do Render cung cấp |
| `FRONTEND_ORIGIN` | `https://your-vercel-app.vercel.app` | URL Vercel app |

### 4. Deploy
- Click "Create Web Service"
- Chờ build hoàn tất (có thể mất 10-15 phút do cài đặt dependencies nặng)

### 5. Lấy URL
Sau khi deploy thành công, copy URL backend (vd: `https://your-app.onrender.com`)

## 🌐 Deploy Frontend (Vercel)

### 1. Tạo tài khoản Vercel
- Đăng ký tại [vercel.com](https://vercel.com)
- Kết nối GitHub repository

### 2. Deploy
- Import project từ GitHub
- **Framework Preset**: Other (static HTML)
- **Root Directory**: `src` (chứa `index.html`)

### 3. Cấu hình Environment Variables
Trong Settings > Environment Variables:

| Variable | Value | Mô tả |
|----------|-------|-------|
| `BACKEND_URL` | `https://your-render-app.onrender.com` | URL Render backend |

### 4. Deploy
- Click "Deploy"
- Chờ hoàn tất (thường nhanh)

### 5. Lấy URL
Copy URL frontend (vd: `https://your-app.vercel.app`)

## 🔧 Cập nhật cấu hình

### Backend (Render)
- Thay `FRONTEND_ORIGIN` thành URL Vercel thực tế
- Redeploy nếu cần

### Frontend (Vercel)
- Thay `BACKEND_URL` thành URL Render thực tế
- Redeploy nếu cần

## 🧪 Kiểm tra

### 1. Health check
```bash
curl https://your-render-app.onrender.com/
# Should return HTML content
```

### 2. CORS check
- Mở browser DevTools > Network
- Truy cập frontend, click "Tôi là Người 1"
- Kiểm tra request `/offer` không bị CORS block

### 3. WebRTC test
- Mở 2 tab browser
- Tab 1: click "Tôi là Người 1"
- Tab 2: click "Tôi là Người 2"
- Kiểm tra audio truyền nhận

## 🔍 Troubleshooting

### Backend không start
- Check logs trên Render dashboard
- Đảm bảo `requirements.txt` đầy đủ
- Kiểm tra memory/CPU limits

### Frontend không load
- Check Vercel build logs
- Đảm bảo `index.html` trong thư mục `src`

### CORS errors
- Đảm bảo `FRONTEND_ORIGIN` chính xác
- Check HTTPS URLs (Vercel/Render đều HTTPS)

### WebRTC không kết nối
- Check STUN server: `stun:stun.l.google.com:19302`
- Đảm bảo browser hỗ trợ WebRTC
- Check firewall/proxy

### Audio không hoạt động
- Đảm bảo microphone permissions
- Check browser autoplay policy
- Verify DeepFilterNet model loaded

### Docker issues
- **Build fails**: Check Docker Desktop running, đủ disk space
- **Port conflicts**: Đảm bảo ports 80, 8080 không bị chiếm
- **Memory issues**: Tăng Docker memory limit (4GB+ recommended)
- **GPU not working**: Install NVIDIA Docker, check GPU drivers
- **Model download fails**: Check internet connection, retry build
- **Container exits immediately**: Check logs với `docker-compose logs backend`

## 📊 Performance

### Backend (Render)
- **Free tier**: 750 giờ/tháng, sleep after 15 phút idle
- **Paid plans**: từ $7/tháng cho persistent apps
- **GPU**: cần plan cao cấp cho DeepFilterNet

### Frontend (Vercel)
- **Free tier**: đủ cho static sites
- **CDN**: global distribution tự động

## 🔒 Security

- CORS chỉ cho phép origin cụ thể
- HTTPS tự động trên cả Vercel và Render
- Không expose sensitive env vars

## 📝 Notes

- DeepFilterNet model ~500MB, build time lâu
- WebRTC yêu cầu HTTPS cho production
- Test trên multiple browsers (Chrome, Firefox, Safari)
- Monitor resource usage trên Render dashboard

## 🛠️ Development Commands

```bash
# Quick commands với Make
make help          # Show all available commands
make build         # Build images
make dev           # Start development
make prod          # Start production
make logs          # View logs
make clean         # Clean up containers
make test          # Run health checks
```

## 🆘 Support

Nếu gặp vấn đề:
1. Check logs trên platform dashboards
2. Verify env vars
3. Test local trước khi deploy
4. Check network/firewall issues</content>
<parameter name="filePath">e:/Pet project/webrtc/README.deployment.md