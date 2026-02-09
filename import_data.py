import sqlite3
import csv
from db_utils import get_connection

DB = "tgsim.db"

# -------------------- COUNTRIES --------------------
def import_countries(cursor):
    with open("data/countries.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO countries (code, name, culture, religion, unrest)
                VALUES (?, ?, ?, ?, ?)
            """, (
                row["code"],
                row["name"],
                row.get("culture", "Unknown"),
                row.get("religion", "Unknown"),
                int(row.get("unrest", 0))
            ))

# -------------------- STATES --------------------
def import_states(cursor):
    with open("data/states.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO states (name, food, stability, loyalty)
                VALUES (?, ?, ?, ?)
            """, (
                row["name"],
                int(row.get("food", 0)),
                int(row.get("stability", 50)),
                int(row.get("loyalty", 50))
            ))

# -------------------- PROVINCES --------------------
def import_provinces(cursor):
    with open("data/provinces.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO provinces (
                    name, population, owner_country_code,
                    rank, religion, culture, terrain
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row["name"],
                int(row["population"]),
                row.get("owner_country_code"),
                row.get("rank", "settlement"),
                row.get("religion", "Unknown"),
                row.get("culture", "Unknown"),
                row.get("terrain", "plains")
            ))

# -------------------- STATE ↔ PROVINCE LINKS --------------------
def import_state_links(cursor):
    with open("data/state_provinces.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO state_provinces (state_id, province_id)
                VALUES (
                    (SELECT id FROM states WHERE name = ?),
                    (SELECT id FROM provinces WHERE name = ?)
                )
            """, (row["state_name"], row["province_name"]))

# -------------------- MAIN --------------------
def main():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    import_countries(cursor)
    import_states(cursor)
    import_provinces(cursor)
    import_state_links(cursor)

    conn.commit()
    conn.close()
    print("🌍 World data imported successfully.")

if __name__ == "__main__":
    main()