"""Small SQLite-backed matchmaking and presence server for onlineff.html.

Run with: python server.py
Open http://localhost:8000/onlineff.html
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import os
import secrets
import sqlite3
import threading
import time

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "onlineff.sqlite3"
PORT = int(os.environ.get("PORT", "8000"))
CAPACITY = 60
STALE_AFTER = 35
LOBBY_JOIN_WINDOW = 60
DB_LOCK = threading.Lock()


def connect_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect_db() as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS players (
                token TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                match_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                x REAL NOT NULL DEFAULT 0,
                y REAL NOT NULL DEFAULT 0,
                z REAL NOT NULL DEFAULT 0,
                yaw REAL NOT NULL DEFAULT 0,
                health INTEGER NOT NULL DEFAULT 100,
                alive INTEGER NOT NULL DEFAULT 1,
                updated_at REAL NOT NULL,
                FOREIGN KEY(match_id) REFERENCES matches(id)
            );
            CREATE INDEX IF NOT EXISTS players_match ON players(match_id);
        """)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = min(int(self.headers.get("Content-Length", "0")), 10000)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/onlineff.html"
            super().do_GET()
            return
        if parsed.path == "/api/state":
            token = parse_qs(parsed.query).get("token", [""])[0]
            self.handle_state(token)
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "capacity": CAPACITY})
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/join":
                self.handle_join(payload)
            elif parsed.path == "/api/update":
                self.handle_update(payload)
            elif parsed.path == "/api/attack":
                self.handle_attack(payload)
            elif parsed.path == "/api/leave":
                self.handle_leave(payload)
            else:
                self.send_json({"error": "Unknown API route"}, 404)
        except (ValueError, TypeError, sqlite3.Error) as exc:
            self.send_json({"error": str(exc)}, 400)

    def handle_join(self, payload):
        now = time.time()
        token = secrets.token_urlsafe(24)
        public_id = secrets.token_urlsafe(12)
        name = str(payload.get("name", "Player"))[:20].strip() or "Player"
        with DB_LOCK, connect_db() as db:
            db.execute("DELETE FROM players WHERE updated_at < ?", (now - STALE_AFTER,))
            row = db.execute("""
                SELECT m.id FROM matches m
                LEFT JOIN players p ON p.match_id=m.id
                WHERE m.updated_at > ? AND m.created_at >= ?
                GROUP BY m.id HAVING COUNT(p.token) < ?
                ORDER BY m.created_at ASC LIMIT 1
            """, (now - STALE_AFTER, now - LOBBY_JOIN_WINDOW, CAPACITY)).fetchone()
            if row:
                match_id = row["id"]
            else:
                match_id = db.execute("INSERT INTO matches(created_at, updated_at) VALUES (?, ?)",
                                      (now, now)).lastrowid
            db.execute("INSERT INTO players(token, public_id, match_id, name, updated_at) VALUES (?, ?, ?, ?, ?)",
                       (token, public_id, match_id, name, now))
            db.execute("UPDATE matches SET updated_at=? WHERE id=?", (now, match_id))
            count = db.execute("SELECT COUNT(*) FROM players WHERE match_id=?", (match_id,)).fetchone()[0]
        self.send_json({"token": token, "publicId": public_id, "matchId": match_id, "players": count,
                        "bots": CAPACITY - count, "capacity": CAPACITY})

    def handle_update(self, payload):
        token = str(payload.get("token", ""))
        now = time.time()
        fields = {key: payload.get(key, default) for key, default in
                  (("x", 0), ("y", 0), ("z", 0), ("yaw", 0), ("health", 100))}
        try:
            fields = {key: float(value) for key, value in fields.items()}
        except (ValueError, TypeError):
            self.send_json({"error": "Position and health values must be numeric"}, 400)
            return
        with DB_LOCK, connect_db() as db:
            row = db.execute("SELECT match_id FROM players WHERE token=?", (token,)).fetchone()
            if not row:
                self.send_json({"error": "Session expired"}, 401)
                return
            if fields["health"] <= 0:
                db.execute("""UPDATE players SET x=?, y=?, z=?, yaw=?, health=0, alive=0, updated_at=?
                              WHERE token=?""", (fields["x"], fields["y"], fields["z"], fields["yaw"], now, token))
            else:
                # Client heartbeats must not overwrite damage applied by another player.
                db.execute("UPDATE players SET x=?, y=?, z=?, yaw=?, updated_at=? WHERE token=?",
                           (fields["x"], fields["y"], fields["z"], fields["yaw"], now, token))
            db.execute("UPDATE matches SET updated_at=? WHERE id=?", (now, row["match_id"]))
        self.send_json({"ok": True})

    def handle_state(self, token):
        now = time.time()
        with DB_LOCK, connect_db() as db:
            me = db.execute("SELECT match_id FROM players WHERE token=? AND updated_at > ?",
                            (token, now - STALE_AFTER)).fetchone()
            if not me:
                self.send_json({"error": "Session expired"}, 401)
                return
            db.execute("DELETE FROM players WHERE match_id=? AND updated_at < ?",
                       (me["match_id"], now - STALE_AFTER))
            players = db.execute("""SELECT public_id, name, x, y, z, yaw, health, alive
                                   FROM players WHERE match_id=? AND updated_at > ?""",
                                 (me["match_id"], now - STALE_AFTER)).fetchall()
        roster = [dict(player) for player in players]
        self.send_json({"matchId": me["match_id"], "players": roster,
                        "humans": len(roster), "bots": max(0, CAPACITY - len(roster)),
                        "capacity": CAPACITY})

    def handle_attack(self, payload):
        attacker = str(payload.get("token", ""))
        target_id = str(payload.get("target", ""))
        damage = max(1, min(100, int(payload.get("damage", 34))))
        with DB_LOCK, connect_db() as db:
            source = db.execute("SELECT match_id, alive FROM players WHERE token=?", (attacker,)).fetchone()
            victim = db.execute("SELECT token, match_id, health, alive FROM players WHERE public_id=?", (target_id,)).fetchone()
            if not source or not victim or source["match_id"] != victim["match_id"]:
                self.send_json({"error": "Players are not in the same match"}, 404)
                return
            if not source["alive"] or not victim["alive"]:
                self.send_json({"error": "Player is already eliminated"}, 409)
                return
            health = max(0, victim["health"] - damage)
            db.execute("UPDATE players SET health=?, alive=?, updated_at=? WHERE token=?",
                       (health, int(health > 0), time.time(), victim["token"]))
        self.send_json({"ok": True, "health": health, "eliminated": health == 0})

    def handle_leave(self, payload):
        token = str(payload.get("token", ""))
        with DB_LOCK, connect_db() as db:
            db.execute("DELETE FROM players WHERE token=?", (token,))
        self.send_json({"ok": True})


if __name__ == "__main__":
    init_db()
    print(f"OnlineFF server running on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


