import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.environ.get("INVEST_DB_PATH", os.path.join(os.path.dirname(__file__), "database", "invest_master.db"))

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            shares REAL NOT NULL DEFAULT 0,
            avg_price REAL NOT NULL DEFAULT 0,
            manual_price REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, code)
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, code)
        )
        """)
        con.commit()
    return {"ok": True, "created_at": now}

def _row_to_user(row):
    if not row:
        return None
    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}

def create_user(username, password):
    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        return {"ok": False, "error": "ユーザー名とパスワードを入力して"}
    if len(password) < 4:
        return {"ok": False, "error": "パスワードは4文字以上にして"}
    now = datetime.now().isoformat(timespec="seconds")
    try:
        with _conn() as con:
            cur = con.execute(
                "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                (username, generate_password_hash(password), now)
            )
            con.commit()
            return {"ok": True, "user_id": cur.lastrowid, "user": {"id": cur.lastrowid, "username": username, "created_at": now}}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "このユーザー名はすでに使われています"}

def verify_user(username, password):
    username = str(username or "").strip()
    password = str(password or "")
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return _row_to_user(row)

def get_user(user_id):
    try:
        uid = int(user_id)
    except Exception:
        return None
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return _row_to_user(row)

def seed_default_user():
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        row = con.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
        if row:
            # ローカル版は初期ログイン確実化のため admin / invest123 に戻す
            con.execute("UPDATE users SET password_hash=? WHERE username=?", (generate_password_hash("invest123"), "admin"))
            con.commit()
            return {"ok": True, "reset": True}
        con.execute(
            "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
            ("admin", generate_password_hash("invest123"), now)
        )
        con.commit()
    return {"ok": True, "created": True}
