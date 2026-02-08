#This script sets up the database and its tables for all the relevant data addressed by the game logic.

from db_utils import get_connection
conn = get_connection()
cursor = conn.cursor()

print("Building nations...")
cursor.execute("""CREATE TABLE countries (
    code TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
""")
print("Nation-building completed.")

print("Creating provinces table...")
cursor.execute("""CREATE TABLE IF NOT EXISTS provinces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    population INTEGER NOT NULL,
    owner_country_code TEXT,
    FOREIGN KEY (owner_country_code) REFERENCES countries(code)
);
""")
print("Provinces table created successfully.")

print("Creating the states table...")
cursor.execute("""CREATE TABLE IF NOT EXISTS states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);
""")
print("States table created successfully.")

print("Creating state_provinces table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS state_provinces (
    state_id INTEGER,
    province_id INTEGER,
    PRIMARY KEY (state_id, province_id),
    FOREIGN KEY (state_id) REFERENCES states(id),
    FOREIGN KEY (province_id) REFERENCES provinces(id)
);
""")
print("State_provinces table created successfully.")
print("✅ All tables have been created")

conn.commit()
conn.close()