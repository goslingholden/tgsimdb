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

# ------------ UNIT TYPES -----------------
def import_unit_types(cursor):
    with open("data/unit_types.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO unit_types (
                    name, recruitment_cost, upkeep_cost, attack, defense
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                row["name"],
                int(row.get("recruitment_cost", 0) or 0),
                int(row.get("upkeep_cost", 0) or 0),
                int(row.get("attack", 0) or 0),
                int(row.get("defense", 0) or 0)
            ))

# ------------ COUNTRY UNITS -----------------
def import_country_units(cursor):
    with open("data/country_units.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = row["country_code"]
            unit = row["unit_type"]
            amount = int(row.get("amount", 0) or 0)

            cursor.execute("SELECT id FROM unit_types WHERE name = ?", (unit,))
            unit_id = cursor.fetchone()
            if not unit_id:
                print(f"⚠ Unit type not found: {unit}")
                continue

            cursor.execute("""
                INSERT OR REPLACE INTO country_units (country_code, unit_type_id, amount)
                VALUES (?, ?, ?)
            """, (country, unit_id[0], amount))

# ------------ COUNTRY MILITARY STATS -----------------
def import_country_military(cursor):
    with open("data/country_military.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO country_military (
                    country_code, morale, discipline
                )
                VALUES (?, ?, ?)
            """, (
                row["country_code"],
                float(row.get("morale", 1.0) or 1.0),
                float(row.get("discipline", 1.0) or 1.0)
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
    import_unit_types(cursor)
    import_country_military(cursor)
    import_country_units(cursor)

    conn.commit()
    conn.close()
    print("🌍 World data imported successfully.")

if __name__ == "__main__":
    main()