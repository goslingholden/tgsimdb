import sqlite3
import csv
from db_utils import get_connection

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

# -------------- DEFAULT BUILDINGS -------------
def import_building_types(cursor):
    with open("data/building_types.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO building_types 
                (name, base_cost, base_tax_income, base_production, base_upkeep, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row["name"],
                int(row.get("base_cost", 0) or 0),
                int(row.get("base_tax_income", 0) or 0),
                int(row.get("base_production", 0) or 0),
                int(row.get("base_upkeep", 0) or 0),
                row.get("description", "")
            ))

# ------------- PROVINCE BUILDINGS ------------
def import_province_buildings(cursor):
    with open("data/province_buildings.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            province = row["province_name"]
            building = row["building_name"]
            amount = int(row.get("amount", 1) or 1)
            cursor.execute("SELECT id FROM provinces WHERE name = ?", (province,))
            province_id = cursor.fetchone()
            cursor.execute("SELECT id FROM building_types WHERE name = ?", (building,))
            building_id = cursor.fetchone()
            if not province_id:
                print(f"⚠ Province not found: {province}")
                continue
            if not building_id:
                print(f"⚠ Building type not found: {building}")
                continue
            cursor.execute("""
                INSERT OR REPLACE INTO province_buildings (province_id, building_type_id, amount)
                VALUES (?, ?, ?)
            """, (province_id[0], building_id[0], amount))

# ------------ COUNTRY ECONOMY -----------------
def import_country_economy(cursor):
    with open("data/country_economy.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO country_economy (
                    country_code, treasury, tax_rate
                )
                VALUES (?, ?, ?)
                """, (
                    row["country_code"],
                    int(row.get("treasury", 0) or 0),
                    float(row.get("tax_rate", 0) or 0)
                ))

# -------------------- MAIN --------------------
def main():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    import_countries(cursor)
    import_states(cursor)
    import_provinces(cursor)
    import_state_links(cursor)
    import_building_types(cursor)
    import_province_buildings(cursor)
    import_country_economy(cursor)
    conn.commit()
    conn.close()
    print("🌍 World data imported successfully.")

if __name__ == "__main__":
    main()