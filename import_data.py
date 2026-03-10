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
    get_land_military_upkeep,
    get_navy_upkeep,
    get_total_navy_units,
    get_total_land_units,
    get_coastal_province_count,
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
                INSERT INTO countries (code, name, capital, culture, 
                    culture_group, religion, government, stability, 
                    unrest, corruption, at_war, war_exhaustion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    capital = excluded.capital,
                    culture = excluded.culture,
                    culture_group = excluded.culture_group,
                    religion = excluded.religion,
                    government = excluded.government,
                    stability = excluded.stability,
                    unrest = excluded.unrest,
                    corruption = excluded.corruption,
                    at_war = excluded.at_war,
                    war_exhaustion = excluded.war_exhaustion
            """, (
                row["code"],
                row["name"],
                row.get("capital", "Unknown"),
                row.get("culture", "Unknown"),
                row.get("culture_group", "Unknown"),
                row.get("religion", "Unknown"),
                row.get("government", "Unknown"),
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
                INSERT INTO provinces (
                    name, population, owner_country_code,
                    rank, religion, culture, terrain, is_naval, resource_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    population = excluded.population,
                    owner_country_code = excluded.owner_country_code,
                    rank = excluded.rank,
                    religion = excluded.religion,
                    culture = excluded.culture,
                    terrain = excluded.terrain,
                    is_naval = excluded.is_naval,
                    resource_id = excluded.resource_id
            """, (
                row["name"],
                int(row["population"]),
                row.get("owner_country_code"),
                row.get("rank", "settlement"),
                row.get("religion", "Unknown"),
                row.get("culture", "Unknown"),
                row.get("terrain", "plains"),
                float(row.get("is_naval", 0)),
                resource_id
            ))

# -------------- DEFAULT BUILDINGS -------------
def import_building_types(cursor):
    with open("data/building_types.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO building_types 
                (name, building_type, base_cost, base_tax_income, base_production, base_upkeep, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    building_type = excluded.building_type,
                    base_cost = excluded.base_cost,
                    base_tax_income = excluded.base_tax_income,
                    base_production = excluded.base_production,
                    base_upkeep = excluded.base_upkeep,
                    description = excluded.description
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
                INSERT INTO unit_types (
                    name, unit_category, recruitment_cost, upkeep_cost, attack, defense
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    unit_category = excluded.unit_category,
                    recruitment_cost = excluded.recruitment_cost,
                    upkeep_cost = excluded.upkeep_cost,
                    attack = excluded.attack,
                    defense = excluded.defense
            """, (
                row["name"],
                row.get("unit_category"),
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
            unit = row["unit_type"].strip()
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
                INSERT INTO resources (name, description)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description
            """, (
                row["name"],
                row.get("description", "")
            ))

# -------- BUILDING RESOURCE COSTS ----------
def import_building_resource_costs(cursor):
    with open("data/building_resource_cost.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_name = row.get("building_name", "").strip()
            resource_name = row.get("resource_name", "").strip()
            amount_per_unit = int(row.get("amount_per_unit", 0) or 0)

            cursor.execute("SELECT id FROM building_types WHERE name = ?", (building_name,))
            building = cursor.fetchone()
            if not building:
                print(f"⚠ Building type not found in resource costs: {building_name}")
                continue

            cursor.execute("SELECT id FROM resources WHERE name = ?", (resource_name,))
            resource = cursor.fetchone()
            if not resource:
                print(f"⚠ Resource not found in building resource costs: {resource_name}")
                continue

            cursor.execute("""
                INSERT INTO building_resource_costs (building_type_id, resource_id, amount_per_unit)
                VALUES (?, ?, ?)
                ON CONFLICT(building_type_id, resource_id) DO UPDATE SET
                    amount_per_unit = excluded.amount_per_unit
            """, (building[0], resource[0], amount_per_unit))


# -------- UNIT RESOURCE COSTS --------------
def import_unit_resource_costs(cursor):
    with open("data/unit_resource_costs.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            unit_name = row.get("unit_name", "").strip()
            resource_name = row.get("resource_name", "").strip()
            amount_per_unit = int(row.get("amount_per_unit", 0) or 0)

            cursor.execute("SELECT id FROM unit_types WHERE name = ?", (unit_name,))
            unit = cursor.fetchone()
            if not unit:
                print(f"⚠ Unit type not found in resource costs: {unit_name}")
                continue

            cursor.execute("SELECT id FROM resources WHERE name = ?", (resource_name,))
            resource = cursor.fetchone()
            if not resource:
                print(f"⚠ Resource not found in unit resource costs: {resource_name}")
                continue

            cursor.execute("""
                INSERT INTO unit_resource_costs (unit_type_id, resource_id, amount_per_unit)
                VALUES (?, ?, ?)
                ON CONFLICT(unit_type_id, resource_id) DO UPDATE SET
                    amount_per_unit = excluded.amount_per_unit
            """, (unit[0], resource[0], amount_per_unit))


def validate_schema(cursor):
    required_tables = [
        "countries", "provinces", "country_economy",
        "building_types", "province_buildings", "building_effects",
        "country_modifiers", "unit_types", "country_units",
        "resources", "country_resources",
        "building_resource_costs", "unit_resource_costs"
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

        treasury, tax_rate = row

        population = get_population(cursor, country)
        provinces = get_province_count(cursor, country)

        tax_eff = get_country_modifier(cursor, country, "tax_efficiency") * \
                  get_building_country_modifier(cursor, country, "tax_efficiency")

        admin_mod = get_country_modifier(cursor, country, "admin_cost_modifier") * \
                    get_building_country_modifier(cursor, country, "admin_cost_modifier")
        admin_eff = get_country_modifier(cursor, country, "admin_efficiency") * \
                    get_building_country_modifier(cursor, country, "admin_efficiency")
        admin_mod /= max(0.0001, admin_eff)

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

        land_unit_limit = int((population * BASE_UNIT_RATIO * unit_limit_mod) / POP_PER_UNIT + 5)

        production = get_resource_production(cursor, country)
        resource_cap = provinces * RESOURCE_CAP_PER_PROVINCE
        stockpile_total = cursor.execute(
            "SELECT COALESCE(SUM(stockpile), 0) FROM country_resources WHERE country_code = ?",
            (country,)
        ).fetchone()[0] or 0

        total_income = int(tax_income + building_income)
        total_expenses = int(administration_cost + military_upkeep + building_upkeep)
        new_treasury = treasury + total_income - total_expenses

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

        # --- Military unit calculations ---
        land_military_upkeep = get_land_military_upkeep(cursor, country)
        navy_upkeep_raw = get_navy_upkeep(cursor, country)
        land_military_upkeep_final = land_military_upkeep * upkeep_mod
        navy_upkeep_mod = get_country_modifier(cursor, country, "navy_upkeep_modifier")
        navy_upkeep_mod *= 1.0  # No political mods in import snapshot
        navy_military_upkeep_final = navy_upkeep_raw * navy_upkeep_mod
        
        # --- Navy info ---
        total_navy_units = get_total_navy_units(cursor, country)
        coastal_provinces = get_coastal_province_count(cursor, country)
        config_local = configparser.ConfigParser()
        config_local.read("config.ini")
        naval_cap_multiplier = int(config_local.get("military", "naval_cap_per_coastal_province", fallback=10))
        navy_cap = coastal_provinces * naval_cap_multiplier
        
        # --- Land units ---
        total_land_units = get_total_land_units(cursor, country)

        print(
            f"\n=== {country} DEBUG INFO ==="
            f"\nPopulation: {population:,} (provinces: {provinces})"
            f"\nLand Units: {total_land_units:,}/{land_unit_limit:,}"
            f"\nNavy Units: {total_navy_units:,}/{navy_cap:,} (coastal: {coastal_provinces})"
            f"\nTax Income: {int(tax_income):,}"
            f"\nBuilding Income: {int(building_income):,}"
            f"\nTotal Income: {total_income:,}"
            f"\nAdministration Cost: {int(administration_cost):,}"
            f"\nLand Military Upkeep: {int(land_military_upkeep_final):,}"
            f"\nNavy Military Upkeep: {int(navy_military_upkeep_final):,}"
            f"\nBuilding Upkeep: {int(building_upkeep):,}"
            f"\nTotal Expenses: {total_expenses:,}"
            f"\nTreasury: {treasury:,} → {new_treasury:,}"
            f"\nResource Cap: {resource_cap:,} | Total Stockpile: {stockpile_total:,}"
            f"\nResource Production: {production if production else 'None'}"
            f"\n--------------------------------------------------")

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
        import_building_resource_costs(cursor)
        import_province_buildings(cursor)
        import_country_economy(cursor)
        import_unit_types(cursor)
        import_unit_resource_costs(cursor)
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