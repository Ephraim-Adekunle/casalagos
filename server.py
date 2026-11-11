#!/usr/bin/env python3
"""Local Casa Lagos companion prototype. Standard library only; binds to localhost."""
from __future__ import annotations
import hashlib, hmac, json, os, re, secrets, sqlite3, time
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CASA_DB_PATH", ROOT / "data" / "casa_lagos.sqlite3"))
HOST = os.environ.get("CASA_HOST", "127.0.0.1")
PORT = int(os.environ.get("CASA_PORT", "8766"))
ITERATIONS = 260_000
SESSION_SECONDS = 60 * 60 * 24 * 14
PRICES = {"calendar":300,"bucket":400,"chair":500,"poster":600,"plant":700,"sofa":10200,"rug":2600,"adire":5400,"gold_sofa":55000,"persian":4500000,"lion":50000000}
HOMES = {"mushin","yaba","lekki","ikate","magodo","ikoyi","banana"}
STYLES = {"starter","homey","statement","regal","custom"}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS designs (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL, home_id TEXT NOT NULL, style TEXT NOT NULL,
          items_json TEXT NOT NULL, total INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          event TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS activity_created_at ON activity(created_at DESC);
        CREATE INDEX IF NOT EXISTS designs_user_id ON designs(user_id, created_at DESC);
        """)
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        cutoff = datetime.fromtimestamp(time.time() - 90*86400, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        con.execute("DELETE FROM activity WHERE created_at < ?", (cutoff,))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${result.hex()}"


def verify_password(password: str, saved: str) -> bool:
    try:
        _scheme, rounds, salt_hex, expected = saved.split("$", 3)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "CasaLagosPrototype/1.0"

    def log_message(self, fmt, *args):
        # Avoid writing usernames or request data to the console.
        return

    def send_json(self, status, body, extra_headers=None):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k,v in (extra_headers or []): self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)

    def body(self):
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: raise ValueError("Invalid request size")
        if length > 128_000: raise ValueError("Request is too large")
        raw = self.rfile.read(length)
        try: data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError("Send valid JSON")
        if not isinstance(data, dict): raise ValueError("Send a JSON object")
        return data

    def origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin: return True
        parsed = urlparse(origin)
        return parsed.netloc == self.headers.get("Host")

    def current_user(self):
        jar = cookies.SimpleCookie()
        try: jar.load(self.headers.get("Cookie", ""))
        except cookies.CookieError: return None
        morsel = jar.get("casa_session")
        if not morsel: return None
        token_hash = hashlib.sha256(morsel.value.encode()).hexdigest()
        with db() as con:
            row = con.execute("SELECT users.id, users.username, sessions.expires_at FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=?",(token_hash,)).fetchone()
            if not row: return None
            if row["expires_at"] < int(time.time()):
                con.execute("DELETE FROM sessions WHERE token_hash=?",(token_hash,)); return None
            return {"id":row["id"],"username":row["username"]}

    def set_session(self, user_id):
        token = secrets.token_urlsafe(32); token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = int(time.time()) + SESSION_SECONDS
        with db() as con:
            con.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",(token_hash,user_id,expires))
            con.execute("INSERT INTO activity(user_id,event,created_at) VALUES(?,?,?)",(user_id,"login",now_iso()))
        secure = "; Secure" if os.environ.get("CASA_HTTPS") == "1" else ""
        header = f"casa_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECONDS}{secure}"
        return [("Set-Cookie",header)]

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health": return self.send_json(200,{"ok":True,"database":"sqlite"})
        if path == "/api/me":
            user = self.current_user()
            return self.send_json(200,{"user":{"username":user["username"]} if user else None})
        if path == "/api/designs":
            user=self.current_user()
            if not user: return self.send_json(401,{"error":"Sign in to load saved Casa Lagos plans."})
            with db() as con:
                rows=con.execute("SELECT id,name,home_id,style,items_json,total,created_at FROM designs WHERE user_id=? ORDER BY id DESC LIMIT 50",(user["id"],)).fetchall()
            return self.send_json(200,{"designs":[{"id":r["id"],"name":r["name"],"home_id":r["home_id"],"style":r["style"],"items":json.loads(r["items_json"]),"total":r["total"],"created_at":r["created_at"]} for r in rows]})
        if path == "/api/admin/activity":
            token=os.environ.get("CASA_ADMIN_TOKEN","")
            supplied=self.headers.get("X-Admin-Token","")
            if not token: return self.send_json(503,{"error":"Owner activity is disabled. Set CASA_ADMIN_TOKEN before starting the server."})
            if not hmac.compare_digest(token,supplied): return self.send_json(403,{"error":"Owner token is incorrect."})
            with db() as con:
                cutoff = datetime.fromtimestamp(time.time() - 90*86400, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                con.execute("DELETE FROM activity WHERE created_at < ?", (cutoff,))
                rows=con.execute("SELECT activity.id,activity.created_at,users.username FROM activity JOIN users ON users.id=activity.user_id WHERE activity.event='login' ORDER BY activity.id DESC LIMIT 100").fetchall()
            return self.send_json(200,{"logins":[{"id":r["id"],"username":r["username"],"created_at":r["created_at"]} for r in rows]})
        return self.serve_file(path)

    def do_POST(self):
        if not self.origin_ok(): return self.send_json(403,{"error":"Cross-site request blocked."})
        path=urlparse(self.path).path
        try: data=self.body()
        except ValueError as e: return self.send_json(400,{"error":str(e)})
        if path in ("/api/auth/register","/api/auth/login"):
            username=data.get("username"); password=data.get("password")
            if not isinstance(username,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,24}",username): return self.send_json(400,{"error":"Use a 3–24 character username (letters, numbers, dot, dash or underscore)."})
            if not isinstance(password,str) or len(password)<10 or len(password)>128: return self.send_json(400,{"error":"Use a unique password with at least 10 characters."})
            with db() as con:
                row=con.execute("SELECT id,username,password_hash FROM users WHERE username=? COLLATE NOCASE",(username,)).fetchone()
                if path.endswith("register"):
                    if row: return self.send_json(409,{"error":"That Casa Lagos username is already in use."})
                    cur=con.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",(username,password_hash(password),now_iso()))
                    user_id=cur.lastrowid
                else:
                    if not row or not verify_password(password,row["password_hash"]): return self.send_json(401,{"error":"Username or password is incorrect."})
                    user_id=row["id"]
            return self.send_json(200,{"user":{"username":username}},self.set_session(user_id))
        if path == "/api/auth/logout":
            jar=cookies.SimpleCookie()
            try: jar.load(self.headers.get("Cookie",""))
            except cookies.CookieError: pass
            morsel=jar.get("casa_session")
            if morsel:
                with db() as con: con.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(morsel.value.encode()).hexdigest(),))
            return self.send_json(200,{"ok":True},[("Set-Cookie","casa_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")])
        if path == "/api/designs":
            user=self.current_user()
            if not user: return self.send_json(401,{"error":"Sign in to save a Casa Lagos plan."})
            name=data.get("name"); home=data.get("home_id"); style=data.get("style"); selected=data.get("items")
            if not isinstance(name,str) or not 1<=len(name.strip())<=80: return self.send_json(400,{"error":"Give this plan a name (up to 80 characters)."})
            if home not in HOMES: return self.send_json(400,{"error":"Choose one of the listed Lagos Life homes."})
            if style not in STYLES: return self.send_json(400,{"error":"Choose a valid room look."})
            if not isinstance(selected,list) or len(selected)>20 or any(not isinstance(x,str) or x not in PRICES for x in selected): return self.send_json(400,{"error":"The item list is not valid."})
            selected=list(dict.fromkeys(selected)); total=sum(PRICES[x] for x in selected)
            with db() as con:
                con.execute("INSERT INTO designs(user_id,name,home_id,style,items_json,total,created_at) VALUES(?,?,?,?,?,?,?)",(user["id"],name.strip(),home,style,json.dumps(selected),total,now_iso()))
            return self.send_json(201,{"ok":True,"total":total})
        return self.send_json(404,{"error":"Not found"})

    def serve_file(self, path):
        if path in ("/","/index.html"): path="/index.html"
        candidate=(ROOT / unquote(path.lstrip("/"))).resolve()
        try: candidate.relative_to(ROOT)
        except ValueError: return self.send_json(404,{"error":"Not found"})
        if not candidate.is_file(): return self.send_json(404,{"error":"Not found"})
        mime={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"text/javascript; charset=utf-8",".svg":"image/svg+xml",".png":"image/png"}.get(candidate.suffix,"application/octet-stream")
        raw=candidate.read_bytes(); self.send_response(200); self.send_header("Content-Type",mime); self.send_header("Content-Length",str(len(raw))); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Referrer-Policy","same-origin"); self.end_headers(); self.wfile.write(raw)

if __name__ == "__main__":
    init_db()
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
