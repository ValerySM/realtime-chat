import os
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room as sio_join_room, leave_room as sio_leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

# -----------------------------
# Config
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
# Для dev укажем явный фронт, иначе с credentials нельзя ставить '*'
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# Flask-CORS (основные заголовки; preflight мы ещё прикроем вручную)
CORS(
    app,
    resources={r"/*": {"origins": [FRONTEND_ORIGIN]}},
    supports_credentials=True,
    expose_headers=["Content-Type", "Authorization"],
)

socketio = SocketIO(
    app,
    cors_allowed_origins=[FRONTEND_ORIGIN],
    async_mode="threading",
)

# -----------------------------
# In-memory stores (demo)
# -----------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

# пользователи текущих сокет-сессий: sid -> {username, room}
users = {}
# база учёток: username -> {password_hash}
users_db = {}
# комнаты и сообщения: room -> [ {id, username, message, timestamp, isSticker, readBy[]} ]
rooms = {
    "general": [],
    "random": [],
    "tech-talk": [],
}

# -----------------------------
# Helpers (auth)
# -----------------------------
def create_token(username: str) -> str:
    payload = {"sub": username, "iat": int(datetime.now(timezone.utc).timestamp())}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str):
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return data.get("sub")
    except Exception:
        return None

def current_username():
    # username, сохранённый при connect (если токен валиден)
    rec = users.get(request.sid) or {}
    return rec.get("username")

def ensure_room(name: str) -> str:
    if not name:
        return "general"
    clean = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "-" )
    if not clean:
        clean = "general"
    if clean not in rooms:
        rooms[clean] = []
        # сообщим всем о новых комнатах
        socketio.emit("rooms_update", {"rooms": sorted(rooms.keys())})
    return clean

def room_usernames(room: str):
    r = []
    for _, info in users.items():
        if info.get("room") == room and info.get("username"):
            r.append(info["username"])
    return sorted(list(set(r)))

def system_message(text: str):
    return {
        "id": str(uuid4()),
        "username": "System",
        "message": text,
        "timestamp": now_iso(),
        "isSticker": False,
        "readBy": [],
    }

# -----------------------------
# CORS: гарантируем заголовки на все ответы
# -----------------------------
@app.after_request
def add_cors_headers(response):
    # Даже если 4xx, чтобы preflight не падал по CORS
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_ORIGIN
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# Явные preflight для auth
@app.route("/auth/register", methods=["OPTIONS"])
@app.route("/auth/login", methods=["OPTIONS"])
def auth_preflight():
    # 204 No Content на preflight — браузеру ок
    return ("", 204)

# -----------------------------
# REST API
# -----------------------------
@app.get("/rooms")
def http_rooms():
    return jsonify({"rooms": sorted(rooms.keys())})

# --- Auth (demo, in-memory) ---
@app.post("/auth/register")
def http_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    if username in users_db:
        return jsonify({"ok": False, "error": "user exists"}), 409
    users_db[username] = {"password_hash": generate_password_hash(password)}
    return jsonify({"ok": True}), 201

@app.post("/auth/login")
def http_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    rec = users_db.get(username)
    if not rec or not check_password_hash(rec["password_hash"], password):
        return jsonify({"ok": False, "error": "invalid credentials"}), 401
    token = create_token(username)
    return jsonify({"ok": True, "token": token, "username": username}), 200

# -----------------------------
# Socket.IO events
# -----------------------------
@socketio.on("connect")
def on_connect(auth=None):
    token = None
    if isinstance(auth, dict):
        token = auth.get("token")
    token = token or request.args.get("token")
    username = decode_token(token) if token else None
    # подготовим запись; комнату выставим при join
    users[request.sid] = {"username": username, "room": None}
    emit("connected", {"message": "Connected", "time": now_iso()})

@socketio.on("disconnect")
def on_disconnect():
    info = users.pop(request.sid, {})
    room = info.get("room")
    username = info.get("username")
    if room and username:
        socketio.emit("user_left", {"message": f"{username} left {room}"}, to=room)
        socketio.emit("user_list_update", {"users": room_usernames(room)}, to=room)

@socketio.on("get_rooms")
def on_get_rooms():
    emit("rooms_update", {"rooms": sorted(rooms.keys())})

@socketio.on("create_room")
def on_create_room(data):
    name = ensure_room((data or {}).get("room"))
    # просто возвращаем обновление списка всем (ensure_room уже эмитит)
    emit("rooms_update", {"rooms": sorted(rooms.keys())}, broadcast=True)

@socketio.on("join_room")
def on_join_room(data):
    room = ensure_room((data or {}).get("room"))
    info = users.get(request.sid) or {}
    username = info.get("username") or (data or {}).get("username") or f"user-{request.sid[:5]}"
    # покинем прежнюю
    old_room = info.get("room")
    if old_room and old_room != room:
        sio_leave_room(old_room)
        socketio.emit("user_left", {"message": f"{username} left {old_room}"}, to=old_room)
        socketio.emit("user_list_update", {"users": room_usernames(old_room)}, to=old_room)
    # зайдём в новую
    users[request.sid] = {"username": username, "room": room}
    sio_join_room(room)
    # история комнатных сообщений только для подключившегося
    emit("message_history", {"messages": rooms[room] or []})
    # системное уведомление
    socketio.emit("user_joined", {"message": f"{username} joined {room}"}, to=room)
    socketio.emit("user_list_update", {"users": room_usernames(room)}, to=room)

@socketio.on("switch_room")
def on_switch_room(data):
    # для совместимости с фронтом — то же, что join_room
    on_join_room(data)

@socketio.on("send_message")
def on_send_message(data):
    info = users.get(request.sid) or {}
    username = info.get("username") or f"user-{request.sid[:5]}"
    room = info.get("room") or "general"
    text = (data or {}).get("message", "").strip()
    if not text:
        return
    msg = {
        "id": str(uuid4()),
        "username": username,
        "message": text,
        "timestamp": now_iso(),
        "isSticker": False,
        "readBy": [],
    }
    rooms[room].append(msg)
    socketio.emit("message_received", msg, to=room)

@socketio.on("send_sticker")
def on_send_sticker(data):
    info = users.get(request.sid) or {}
    username = info.get("username") or f"user-{request.sid[:5]}"
    room = info.get("room") or "general"
    emoji = (data or {}).get("emoji", "").strip()
    if not emoji:
        return
    msg = {
        "id": str(uuid4()),
        "username": username,
        "message": emoji,       # фронт показывает крупным, если isSticker=True
        "timestamp": now_iso(),
        "isSticker": True,
        "readBy": [],
    }
    rooms[room].append(msg)
    socketio.emit("message_received", msg, to=room)

@socketio.on("typing")
def on_typing(data):
    info = users.get(request.sid) or {}
    username = info.get("username") or f"user-{request.sid[:5]}"
    room = info.get("room") or "general"
    typing = bool((data or {}).get("typing"))
    socketio.emit("typing", {"username": username, "typing": typing}, to=room, include_self=False)

@socketio.on("mark_read")
def on_mark_read(data):
    # data: { id } — пометим сообщение как прочитанное текущим пользователем
    info = users.get(request.sid) or {}
    username = info.get("username")
    room = info.get("room")
    msg_id = (data or {}).get("id")
    if not (username and room and msg_id):
        return
    updated = None
    for m in rooms.get(room, []):
        if m["id"] == msg_id:
            if username not in m["readBy"]:
                m["readBy"].append(username)
            updated = {"id": m["id"], "readBy": m["readBy"]}
            break
    if updated:
        socketio.emit("message_read_update", updated, to=room)

# -----------------------------
# Entry
# -----------------------------
if __name__ == "__main__":
    # Для отладки: доступ извне, WebSocket+Polling
    socketio.run(app, host=HOST, port=PORT, debug=True)
