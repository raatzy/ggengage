import sqlite3
import os
from datetime import datetime
from .config import Config


def get_db():
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email_from      TEXT,
                email_subject   TEXT,
                email_body      TEXT,
                generated_text  TEXT,
                image_path      TEXT,
                hashtags        TEXT,
                referral_link   TEXT,
                platforms       TEXT DEFAULT 'facebook,instagram',
                status          TEXT DEFAULT 'pending',
                post_results    TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at     TIMESTAMP,
                posted_at       TIMESTAMP,
                notes           TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                message_id   TEXT PRIMARY KEY,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def already_processed(message_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None


def mark_processed(message_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_emails (message_id) VALUES (?)",
            (message_id,),
        )
        conn.commit()


def save_post(
    email_from, email_subject, email_body,
    generated_text, image_path, hashtags, referral_link
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO posts
               (email_from, email_subject, email_body, generated_text,
                image_path, hashtags, referral_link)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (email_from, email_subject, email_body,
             generated_text, image_path, hashtags, referral_link),
        )
        conn.commit()
        return cur.lastrowid


def get_post(post_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()


def get_posts(status=None):
    with get_db() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        return conn.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()


def update_post(post_id: int, generated_text: str, hashtags: str, platforms: str, notes: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE posts SET generated_text=?, hashtags=?, platforms=?, notes=? WHERE id=?",
            (generated_text, hashtags, platforms, notes, post_id),
        )
        conn.commit()


def set_status(post_id: int, status: str):
    with get_db() as conn:
        approved_at = datetime.utcnow() if status == "approved" else None
        conn.execute(
            "UPDATE posts SET status=?, approved_at=? WHERE id=?",
            (status, approved_at, post_id),
        )
        conn.commit()


def set_posted(post_id: int, results: str):
    """Mark as posted and store JSON results string."""
    with get_db() as conn:
        conn.execute(
            "UPDATE posts SET status='posted', posted_at=?, post_results=? WHERE id=?",
            (datetime.utcnow(), results, post_id),
        )
        conn.commit()
