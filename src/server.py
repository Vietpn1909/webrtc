"""
Hybrid WebRTC Signaling Server
Enables 2 computers to connect and call each other with AI audio processing
"""

import asyncio
import json
import logging
import os
import socket
import ssl
import uuid
from pathlib import Path

from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hybrid-webrtc")

# Store active rooms
rooms = {}  # room_id -> {users: {}, offer: None, answer: None, ice_candidates: {}}


async def index(request):
    """Serve the main HTML page"""
    content = open(Path(__file__).parent / "index.html", "r", encoding="utf-8").read()
    return web.Response(content_type="text/html", text=content)


async def create_room(request):
    """Create a new room and return room ID"""
    room_id = str(uuid.uuid4())[:8]
    rooms[room_id] = {"users": {}, "offer": None, "answer": None, "ice_candidates": {}}
    logger.info(f"Created room: {room_id}")
    return web.json_response({"room_id": room_id})


async def join_room(request):
    """Join an existing room"""
    data = await request.json()
    room_id = data.get("room_id")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    user_id = str(uuid.uuid4())[:8]
    room = rooms[room_id]
    
    if len(room["users"]) >= 2:
        return web.json_response({"error": "Room is full"}, status=400)
    
    room["users"][user_id] = {"joined": True}
    is_caller = len(room["users"]) == 1
    
    logger.info(f"User {user_id} joined room {room_id} as {'caller' if is_caller else 'callee'}")
    return web.json_response({
        "user_id": user_id,
        "is_caller": is_caller,
        "users_count": len(room["users"])
    })


async def offer(request):
    """Handle WebRTC offer from caller"""
    data = await request.json()
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    sdp = data.get("sdp")
    sdp_type = data.get("type")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    room["offer"] = {"sdp": sdp, "type": sdp_type, "user_id": user_id}
    
    logger.info(f"Received offer from {user_id} in room {room_id}")
    return web.json_response({"status": "ok"})


async def get_offer(request):
    """Get the offer for callee"""
    room_id = request.query.get("room_id")
    user_id = request.query.get("user_id")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    
    if room["offer"] and room["offer"]["user_id"] != user_id:
        return web.json_response(room["offer"])
    
    return web.json_response({"status": "waiting"})


async def answer(request):
    """Handle WebRTC answer from callee"""
    data = await request.json()
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    sdp = data.get("sdp")
    sdp_type = data.get("type")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    room["answer"] = {"sdp": sdp, "type": sdp_type, "user_id": user_id}
    
    logger.info(f"Received answer from {user_id} in room {room_id}")
    return web.json_response({"status": "ok"})


async def get_answer(request):
    """Get the answer for caller"""
    room_id = request.query.get("room_id")
    user_id = request.query.get("user_id")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    
    if room["answer"] and room["answer"]["user_id"] != user_id:
        return web.json_response(room["answer"])
    
    return web.json_response({"status": "waiting"})


async def ice_candidate(request):
    """Store ICE candidate"""
    data = await request.json()
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    candidate = data.get("candidate")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    
    if user_id not in room["ice_candidates"]:
        room["ice_candidates"][user_id] = []
    
    room["ice_candidates"][user_id].append(candidate)
    
    return web.json_response({"status": "ok"})


async def get_ice_candidates(request):
    """Get ICE candidates from the other user"""
    room_id = request.query.get("room_id")
    user_id = request.query.get("user_id")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    candidates = []
    
    for uid, cands in room["ice_candidates"].items():
        if uid != user_id:
            candidates.extend(cands)
    
    return web.json_response({"candidates": candidates})


async def check_room(request):
    """Check room status"""
    room_id = request.query.get("room_id")
    
    if room_id not in rooms:
        return web.json_response({"error": "Room not found"}, status=404)
    
    room = rooms[room_id]
    return web.json_response({
        "users_count": len(room["users"]),
        "has_offer": room["offer"] is not None,
        "has_answer": room["answer"] is not None
    })


async def leave_room(request):
    """Leave a room"""
    data = await request.json()
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    
    if room_id in rooms and user_id in rooms[room_id]["users"]:
        del rooms[room_id]["users"][user_id]
        logger.info(f"User {user_id} left room {room_id}")
    
    return web.json_response({"status": "ok"})


async def cleanup_rooms():
    """Periodically clean up empty rooms"""
    while True:
        await asyncio.sleep(300)
        empty_rooms = [rid for rid, room in rooms.items() if len(room["users"]) == 0]
        for rid in empty_rooms:
            del rooms[rid]
            logger.info(f"Cleaned up empty room: {rid}")


async def start_background_tasks(app):
    app['cleanup_task'] = asyncio.create_task(cleanup_rooms())


async def cleanup_background_tasks(app):
    app['cleanup_task'].cancel()
    try:
        await app['cleanup_task']
    except asyncio.CancelledError:
        pass


def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/api/create-room", create_room)
    app.router.add_post("/api/join-room", join_room)
    app.router.add_post("/api/offer", offer)
    app.router.add_get("/api/offer", get_offer)
    app.router.add_post("/api/answer", answer)
    app.router.add_get("/api/answer", get_answer)
    app.router.add_post("/api/ice-candidate", ice_candidate)
    app.router.add_get("/api/ice-candidates", get_ice_candidates)
    app.router.add_get("/api/check-room", check_room)
    app.router.add_post("/api/leave-room", leave_room)
    
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    
    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()
    
    # Setup SSL context for HTTPS (required for camera/mic on non-localhost)
    ssl_context = None
    protocol = "http"
    cert_path = Path(__file__).parent / "cert.pem"
    key_path = Path(__file__).parent / "key.pem"
    
    if cert_path.exists() and key_path.exists():
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(str(cert_path), str(key_path))
        protocol = "https"
    else:
        print("\n⚠️  No SSL certificates found. Running without HTTPS.")
        print("   Camera/microphone will only work on localhost.")
        print("   To generate certificates, run:")
        print("   openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes\n")
    
    print("\n" + "="*55)
    print("🚀 Hybrid WebRTC Call Server")
    print("="*55)
    print(f"\n📍 Local access:   {protocol}://localhost:{port}")
    print(f"📍 Network access: {protocol}://{local_ip}:{port}")
    print("\n💡 Share the network URL with the other computer!")
    if protocol == "https":
        print("⚠️  Accept the self-signed certificate warning in browser.")
    print("="*55 + "\n")
    
    web.run_app(app, host="0.0.0.0", port=port, ssl_context=ssl_context, print=None)