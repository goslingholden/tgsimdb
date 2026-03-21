import sqlite3

DB_FILE = "world.db"
EVENT_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    command_name TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    delta_value REAL,
    notes TEXT
);
"""

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_event_log_table(cursor):
    cursor.execute(EVENT_LOG_TABLE_SQL)
