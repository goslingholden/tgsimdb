import csv
import configparser
from db_utils import get_connection
from economy_tick import (
    get_country_modifier,
    get_building_country_modifier,
    get_population,
    get_province_count,
    get_military_upkeep,
    get_building_economy,
    get_resource_production,
    ensure_country_resource_rows,
)

# ---------------- LOAD CONFIG ----------------
config = configparser.ConfigParser()
config.read("config.ini")

BASE_TAX_PER_POP = float(config["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = float(config["economy"]["admin_cost_per_province"])

RESOURCE_CAP_PER_PROVINCE = int(config["resources"]["resource_cap_per_province"])

POP_PER_UNIT = int(config["military"]["pop_per_unit"])
BASE_UNIT_RATIO = float(config["military"]["base_unit_ratio"])

# -------------------- COUNTRIES --------------------
def import_countries(cursor):
    with open("data/countries.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO countries (code, name, culture, religion, stability, 
                    unrest, corruption, at_war, war_exhaustion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["code"],
                row["name"],
                row.get("culture", "Unknown"),
                row.get("religion", "Unknown"),
                int(row.get("stability", 50)),
                int(row.get("unrest", 0)),
                float(row.get("corruption", 0.0)),
                int(row.get("at_war", 0)),
                int(row.get("war_exhaustion", 0))
            ))

# -------------------- PROVINCES --------------------
def import_provinces(cursor):
    with open("data/provinces.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:

            resource_name = row.get("resource")
            resource_id = None
            if resource_name:
                cursor.execute("SELECT id FROM resources WHERE name = ?", (resource_name,))
                res = cursor.fetchone()
                if res:
                    resource_id = res[0]

            cursor.execute("""
                INSERT OR IGNORE INTO provinces (
                    name, population, owner_country_code,
                    rank, religion, culture, terrain, resource_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["name"],
                int(row["population"]),
                row.get("owner_country_code"),
                row.get("rank", "settlement"),
                row.get("religion", "Unknown"),
                row.get("culture", "Unknown"),
                row.get("terrain", "plains"),
                resource_id
            ))

# -------------- DEFAULT BUILDINGS -------------
def import_building_types(cursor):
    with open("data/building_types.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO building_types 
                (name, building_type, base_cost, base_tax_income, base_production, base_upkeep, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row["name"],
                row.get("building_type", ""),
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
                INSERT INTO country_economy (
                    country_code, treasury, tax_rate
                )
                VALUES (?, ?, ?)
                ON CONFLICT(country_code) DO UPDATE SET
                    treasury = excluded.treasury,
                    tax_rate = excluded.tax_rate
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

# --------------- MODIFIERS -----------------
def import_modifiers(cursor):
    with open("data/modifiers.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO modifiers (
                    modifier_key, description, default_value
                )
                VALUES (?, ?, ?)
                ON CONFLICT(modifier_key) DO UPDATE SET
                    description = excluded.description,
                    default_value = excluded.default_value
            """, (
                row["modifier_key"],
                row.get("description", ""),
                float(row.get("default_value", 1.0) or 1.0)
            ))

# --------------- BUILDING EFFECTS -----------------
def import_building_effects(cursor):
    with open("data/building_effects.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_name = row.get("building_name", "").strip()

            cursor.execute("SELECT id FROM building_types WHERE name = ?", (building_name,))
            result = cursor.fetchone()
            if not result:
                print(f"⚠ Building type not found: '{building_name}' — skipping effect row.")
                continue
            building_type_id = result[0]

            scope = row.get("scope", "")
            modifier_key = row.get("modifier_key", "")
            value = float(row.get("value", 0.0) or 0.0)

            cursor.execute("""
                INSERT INTO building_effects (
                    building_type_id, scope, modifier_key, value
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(building_type_id, scope, modifier_key) DO UPDATE SET
                    value = excluded.value
            """, (building_type_id, scope, modifier_key, value))

# --------------- COUNTRY MODIFIERS -----------------
def import_country_modifiers(cursor):
    with open("data/country_modifiers.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO country_modifiers (
                    country_code, modifier_key, value
                )
                VALUES (?, ?, ?)
                ON CONFLICT(country_code, modifier_key) DO UPDATE SET
                    value = excluded.value
                """, (
                    row["country_code"],
                    row.get("modifier_key", ""),
                    float(row.get("value", 0.0) or 0.0)
                ))

# -------------------- RESOURCES --------------------
def import_resources(cursor):
    with open("data/resources.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT OR IGNORE INTO resources (name, description)
                VALUES (?, ?)
            """, (
                row["name"],
                row.get("description", "")
            ))


def validate_schema(cursor):
    required_tables = [
        "countries", "provinces", "country_economy",
        "building_types", "province_buildings", "building_effects",
        "country_modifiers", "unit_types", "country_units",
        "resources", "country_resources"
    ]

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cursor.fetchall()}

    missing = [t for t in required_tables if t not in existing]
    if missing:
        raise RuntimeError(f"Missing required tables: {missing}")


def import_economy_snapshot(cursor):
    validate_schema(cursor)
    ensure_country_resource_rows(cursor)

    cursor.execute("SELECT code FROM countries")
    countries = [c[0] for c in cursor.fetchall()]

    print("\n=== IMPORT ECONOMY START ===")

    for country in countries:
        cursor.execute("SELECT treasury, tax_rate FROM country_economy WHERE country_code = ?", (country,))
        row = cursor.fetchone()
        if not row:
            print(f"⚠ No economy row for {country}")
            continue

        _, tax_rate = row

        population = get_population(cursor, country)
        provinces = get_province_count(cursor, country)

        tax_eff = get_country_modifier(cursor, country, "tax_efficiency") * \
                  get_building_country_modifier(cursor, country, "tax_efficiency")

        admin_mod = get_country_modifier(cursor, country, "admin_cost_modifier") * \
                    get_building_country_modifier(cursor, country, "admin_cost_modifier") * \
                    get_country_modifier(cursor, country, "admin_efficiency") * \
                    get_building_country_modifier(cursor, country, "admin_efficiency")

        unit_limit_mod = get_country_modifier(cursor, country, "military_unit_limit_mult") * \
                         get_building_country_modifier(cursor, country, "military_unit_limit_mult")

        upkeep_mod = get_country_modifier(cursor, country, "military_upkeep_modifier") * \
                     get_building_country_modifier(cursor, country, "military_upkeep_modifier")

        building_income_mult = get_country_modifier(cursor, country, "production_efficiency") * \
                               get_building_country_modifier(cursor, country, "production_efficiency")

        base_tax = population * BASE_TAX_PER_POP
        tax_income = base_tax * tax_rate * tax_eff

        administration_cost = provinces * ADMIN_COST_PER_PROVINCE * admin_mod

        base_upkeep = get_military_upkeep(cursor, country)
        military_upkeep = base_upkeep * upkeep_mod

        building_income_raw, building_upkeep = get_building_economy(cursor, country)
        building_income = building_income_raw * building_income_mult

        unit_limit = int((population * BASE_UNIT_RATIO * unit_limit_mod) / POP_PER_UNIT + 5)
        total_units = cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM country_units WHERE country_code = ?",
            (country,)
        ).fetchone()[0]

        production = get_resource_production(cursor, country)
        resource_cap = provinces * RESOURCE_CAP_PER_PROVINCE
        stockpile_total = cursor.execute(
            "SELECT COALESCE(SUM(stockpile), 0) FROM country_resources WHERE country_code = ?",
            (country,)
        ).fetchone()[0] or 0

        total_income = int(tax_income + building_income)
        total_expenses = int(administration_cost + military_upkeep + building_upkeep)

        cursor.execute("""
            UPDATE country_economy SET
                tax_income = ?,
                building_income = ?,
                total_income = ?,
                administration_cost = ?,
                military_upkeep = ?,
                building_upkeep = ?,
                total_expenses = ?,
                total_population = ?
            WHERE country_code = ?
        """, (
            int(tax_income),
            int(building_income),
            total_income,
            int(administration_cost),
            int(military_upkeep),
            int(building_upkeep),
            total_expenses,
            population,
            country
        ))

        print(
            f"{country}: pop={population}, prov={provinces}, units={total_units}/{unit_limit}, "
            f"income={total_income}, expenses={total_expenses}, "
            f"resource_cap={resource_cap}, stockpile={stockpile_total}, produced={sum(production.values())}"
        )

    print("✅ IMPORT ECONOMY COMPLETE")

# -------------------- MAIN --------------------
def main():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        import_countries(cursor)
        import_resources(cursor)
        import_provinces(cursor)
        import_building_types(cursor)
        import_province_buildings(cursor)
        import_country_economy(cursor)
        import_unit_types(cursor)
        import_country_units(cursor)
        import_modifiers(cursor)
        import_building_effects(cursor)
        import_country_modifiers(cursor)
        import_economy_snapshot(cursor)

        conn.commit()
        print("🌍 World data and economy snapshot imported successfully.")

    except Exception as e:
        conn.rollback()
        print("❌ Import failed. All changes have been rolled back.")
        print("ERROR:", e)
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    main()
