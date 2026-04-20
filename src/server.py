import asyncio
import json
import logging
import ssl
import os
import sys
import time
from aiohttp import web
import aiohttp_cors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc-signaling")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Lưu trữ các kết nối WebSocket đang hoạt động. Khóa là 'role' (ví dụ: 'user1', 'user2').
connected_clients = {}

async def index(request):
    try:
        content = open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8").read()
        return web.Response(content_type="text/html", text=content)
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        return web.Response(status=404, text="Không tìm thấy index.html")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    current_role = None

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                
                # Việc của server là map đúng người gửi với người nhận
                logger.debug(f"Nhận được message: {data}")
                msg_type = data.get("type")
                
                if msg_type == "join":
                    current_role = data.get("role")
                    if current_role:
                        if current_role in connected_clients and connected_clients[current_role] != ws:
                            logger.info(f"Đóng kết nối cũ của {current_role}")
                            try:
                                await connected_clients[current_role].close()
                            except:
                                pass
                        
                        connected_clients[current_role] = ws
                        logger.info(f"==> Tài khoản {current_role} đã kết nối lên WebSocket.")
                        
                        # Báo lại cho client biết là ok
                        await ws.send_json({"type": "joined", "role": current_role})
                        
                        # Báo cho peer kia nếu họ đã online để bắt đầu đàm phán (Peer Ready)
                        target_role = "user2" if current_role == "user1" else "user1"
                        if target_role in connected_clients:
                            logger.info(f"Cả 2 đã sẵn sàng. Gửi peer_ready.")
                            await connected_clients[target_role].send_json({"type": "peer_ready"})
                            await ws.send_json({"type": "peer_ready"})
                        
                elif msg_type in ["offer", "answer", "candidate"]:
                    # Đây là luồng P2P Signaling. Nếu mình là user1, cần gửi cho user2 và ngược lại.
                    if current_role == "user1":
                        target_role = "user2"
                    elif current_role == "user2":
                        target_role = "user1"
                    else:
                        continue
                    
                    target_ws = connected_clients.get(target_role)
                    if target_ws is not None and not target_ws.closed:
                        logger.info(f"Chuyển {msg_type} từ {current_role} → {target_role}")
                        await target_ws.send_json(data)
                    else:
                        if target_ws is not None and target_ws.closed:
                            logger.warning(f"{target_role} WS đã closed, dọn dict.")
                            del connected_clients[target_role]
                        else:
                            logger.warning(f"{target_role} chưa kết nối.")
                        
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"Lỗi cú pháp Websocket {ws.exception()}")
    finally:
        if current_role and connected_clients.get(current_role) == ws:
            del connected_clients[current_role]
            logger.warning(f"<== [{time.strftime('%H:%M:%S')}] {current_role} DISCONNECT. "
                           f"ws.closed={ws.closed}, exception={ws.exception()}")

    return ws

async def on_shutdown(app):
    for ws in list(connected_clients.values()):
        await ws.close(code=1001, message='Server shutdown')

if __name__ == "__main__":
    # Proactor event loop trên Windows gây WS bị đóng sớm
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.on_shutdown.append(on_shutdown)

    # Enable CORS for frontend deployments
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    cors.add(app.router.add_resource("/")).add_route("GET", index)

    cert, key = os.path.join(BASE_DIR, "cert.pem"), os.path.join(BASE_DIR, "key.pem")
    ssl_ctx = None
    if os.path.exists(cert) and os.path.exists(key):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert, key)
        logger.info("HTTPS/WSS Enabled")

    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0"

    logger.info(f"Starting generic WebSocket Signaling server on {host}:{port}")
    web.run_app(app, host=host, port=port, ssl_context=ssl_ctx)
