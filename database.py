import sqlite3
from datetime import datetime

DB_FILE = "companion.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_ins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mood_score INTEGER NOT NULL,
            note TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            due_time TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            is_recurring INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS in_progress_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT NOT NULL,
            transcript TEXT NOT NULL,
            language TEXT,
            initial_mood TEXT,
            marked_to_continue INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            topic TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_checkin(mood_score, note):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO check_ins (timestamp, mood_score, note) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), mood_score, note)
    )
    conn.commit()
    conn.close()


def get_recent_checkins(limit=5):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, mood_score, note FROM check_ins ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_progress(conversation_id, transcript_json, language, initial_mood):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if conversation_id is None:
        cursor.execute(
            "INSERT INTO in_progress_conversations (updated_at, transcript, language, initial_mood) VALUES (?, ?, ?, ?)",
            (now, transcript_json, language, initial_mood)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return new_id
    else:
        cursor.execute(
            "UPDATE in_progress_conversations SET updated_at = ?, transcript = ? WHERE id = ?",
            (now, transcript_json, conversation_id)
        )
        conn.commit()
        conn.close()
        return conversation_id


def mark_conversation_continuable(conversation_id, continuable=True):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE in_progress_conversations SET marked_to_continue = ? WHERE id = ?",
        (int(continuable), conversation_id)
    )
    conn.commit()
    conn.close()


def get_continuable_conversations():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, updated_at, transcript FROM in_progress_conversations WHERE marked_to_continue = 1 ORDER BY updated_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_conversation(conversation_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT transcript, language, initial_mood FROM in_progress_conversations WHERE id = ?",
        (conversation_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def delete_conversation(conversation_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM in_progress_conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()


def save_moment(content, topic):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saved_moments (timestamp, content, topic) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), content, topic)
    )
    conn.commit()
    conn.close()


def get_saved_moments(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, content, topic FROM saved_moments ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_task(title, due_date, due_time=None, is_recurring=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, due_date, due_time, status, is_recurring, created_at) VALUES (?, ?, ?, 'pending', ?, ?)",
        (title, due_date, due_time, int(is_recurring), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_all_tasks_for_range(start_date, end_date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, due_date, due_time, status, is_recurring
        FROM tasks
        WHERE is_recurring = 1
           OR (due_date BETWEEN ? AND ? AND status = 'pending')
        ORDER BY due_date ASC, due_time ASC
    """, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_task_done(task_id, for_date=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_recurring FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return
    is_recurring = row[0]

    if is_recurring:
        date = for_date or datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT id FROM recurring_completions WHERE task_id = ? AND date = ?",
            (task_id, date)
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE recurring_completions SET completed = 1 WHERE id = ?", (existing[0],)
            )
        else:
            cursor.execute(
                "INSERT INTO recurring_completions (task_id, date, completed) VALUES (?, ?, 1)",
                (task_id, date)
            )
    else:
        cursor.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))

    conn.commit()
    conn.close()


def is_recurring_done_today(task_id, date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT completed FROM recurring_completions WHERE task_id = ? AND date = ?",
        (task_id, date)
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])