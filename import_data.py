#This script imports the game data stored on CSV files on the database. The provided CSV files in the data folder have all the seeds.

import sqlite3
import csv

DB = "tgsim.db"

# ------------------------
# Utility
# ------------------------

def clean(value):
    """Strip whitespace and handle empty strings."""
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None

# ------------------------
# Import Functions
# ------------------------

def import_countries(cursor):
    print("Importing countries...")
    with open("data/countries.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = clean(row["code"])
            name = clean(row["name"])
            cursor.execute("""
                INSERT OR IGNORE INTO countries (code, name)
                VALUES (?, ?)
            """, (code, name))

def import_states(cursor):
    print("Importing states...")
    with open("data/states.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = clean(row["name"])
            cursor.execute("""
                INSERT OR IGNORE INTO states (name)
                VALUES (?)
            """, (name,))

def import_provinces(cursor):
    print("Importing provinces...")
    with open("data/provinces.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = clean(row["name"])
            owner = clean(row.get("owner_country_code"))

            # Convert population safely
            try:
                population = int(row["population"])
            except ValueError:
                print(f"❌ Invalid population for province {name}: {row['population']}")
                continue

            cursor.execute("""
                INSERT INTO provinces (name, population, owner_country_code)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    population = excluded.population,
                    owner_country_code = excluded.owner_country_code;
            """, (name, population, owner))

def import_state_links(cursor):
    print("Importing state-province links...")
    with open("data/state_provinces.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state_name = clean(row["state_name"])
            province_name = clean(row["province_name"])

            # Lookup state ID
            cursor.execute("SELECT id FROM states WHERE name = ?", (state_name,))
            state = cursor.fetchone()

            # Lookup province ID
            cursor.execute("SELECT id FROM provinces WHERE name = ?", (province_name,))
            province = cursor.fetchone()

            if not state:
                print(f"❌ Missing state: {state_name}")
                continue
            if not province:
                print(f"❌ Missing province: {province_name}")
                continue

            cursor.execute("""
                INSERT OR IGNORE INTO state_provinces (state_id, province_id)
                VALUES (?, ?)
            """, (state[0], province[0]))

# ------------------------
# Main
# ------------------------

def main():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    print("Beginning import transaction...")
    conn.execute("BEGIN TRANSACTION;")

    import_countries(cursor)
    import_states(cursor)
    import_provinces(cursor)
    import_state_links(cursor)

    conn.commit()
    conn.close()
    print("✅ World data imported successfully.")

if __name__ == "__main__":
    main()