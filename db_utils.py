#SQLite utility for ease of use. It creates a "pycache" folder in the main folder.

import sqlite3

DB_FILE = "world.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn