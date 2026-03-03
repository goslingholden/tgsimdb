from db_utils import get_connection
import configparser
from economy_tick import get_country_modifier, get_building_country_modifier, get_population, get_province_count, get_military_upkeep, get_building_economy, get_resource_production

# ---------------- LOAD CONFIG ----------------
config = configparser.ConfigParser()
config.read("config.ini")

BASE_TAX_PER_POP = float(config["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = float(config["economy"]["admin_cost_per_province"])

RESOURCE_PRODUCTION = int(config["resources"]["resource_production"])
RESOURCE_CAP_PER_PROVINCE = int(config["resources"]["resource_cap_per_province"])

POP_PER_UNIT = int(config["military"]["pop_per_unit"])
BASE_UNIT_RATIO = float(config["military"]["base_unit_ratio"])

# ================== DB VALIDATION ==================

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
        print("❌ MISSING TABLES:", missing)
        exit(1)

    cursor.execute("PRAGMA table_info(building_effects)")
    cols = {c[1] for c in cursor.fetchall()}
    if "building_type_id" not in cols:
        print("❌ building_effects MUST reference building_type_id, not name")
        exit(1)

    print("✅ DB schema validated")

# ================== IMPORT ECONOMY ==================

def import_economy():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    validate_schema(cursor)

    cursor.execute("SELECT code FROM countries")
    countries = [c[0] for c in cursor.fetchall()]

    resource_names = {rid: name for rid, name in cursor.execute("SELECT id, name FROM resources").fetchall()}

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

        # ----- MODIFIERS -----
        tax_eff = get_country_modifier(cursor, country, "tax_efficiency") * \
                  get_building_country_modifier(cursor, country, "tax_efficiency")

        admin_mod = get_country_modifier(cursor, country, "admin_cost_modifier") * \
                    get_building_country_modifier(cursor, country, "admin_cost_modifier")

        unit_limit_mod = get_country_modifier(cursor, country, "unit_limit_modifier") * \
                         get_building_country_modifier(cursor, country, "unit_limit_modifier")

        upkeep_mod = get_country_modifier(cursor, country, "military_upkeep_modifier") * \
                     get_building_country_modifier(cursor, country, "military_upkeep_modifier")

        building_income_mult = get_building_country_modifier(cursor, country, "building_income_mult")

        # ----- TAX -----
        base_tax = population * BASE_TAX_PER_POP
        tax_income = base_tax * tax_rate * tax_eff

        # ----- ADMIN -----
        administration_cost = provinces * ADMIN_COST_PER_PROVINCE * admin_mod

        # ----- MILITARY -----
        base_upkeep = get_military_upkeep(cursor, country)
        military_upkeep = base_upkeep * upkeep_mod

        # ----- BUILDINGS -----
        building_income_raw, building_upkeep = get_building_economy(cursor, country)
        building_income = building_income_raw * building_income_mult

        # ----- UNIT LIMIT -----
        unit_limit = int((population * BASE_UNIT_RATIO * unit_limit_mod) / POP_PER_UNIT + 5)
        total_units = cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM country_units WHERE country_code = ?", (country,)).fetchone()[0]

        # ----- RESOURCES -----
        production = get_resource_production(cursor, country)
        resource_cap = provinces * RESOURCE_CAP_PER_PROVINCE

        # Add production to stockpile
        for rid, amount in production.items():
            cursor.execute("""
                INSERT INTO country_resources (country_code, resource_id, stockpile)
                VALUES (?, ?, ?)
                ON CONFLICT(country_code, resource_id)
                DO UPDATE SET stockpile = stockpile + ?
            """, (country, rid, amount, amount))

        # ----- TOTALS -----
        total_income = int(tax_income + building_income)
        total_expenses = int(administration_cost + military_upkeep + building_upkeep)

        # SAVE
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

        # ----- DEBUG OUTPUT -----
        production_named = {resource_names.get(rid, f"ID_{rid}"): amt for rid, amt in production.items()}
        stockpile = cursor.execute("""
            SELECT r.name, cr.stockpile
            FROM country_resources cr
            JOIN resources r ON cr.resource_id = r.id
            WHERE cr.country_code = ?
            ORDER BY r.name
        """, (country,)).fetchall()

        print(f"\n{country}")
        print(f" Population: {population} | Provinces: {provinces}")
        print(f" Tax Eff x{tax_eff:.3f} | Admin Mod x{admin_mod:.3f}")
        print(f" Buildings Raw: Income {building_income_raw}, Upkeep {building_upkeep}")
        print(f" Unit Limit: {total_units}/{unit_limit}")
        print(f" Resource Cap: {resource_cap} | Total Stockpile: {sum(s[1] for s in stockpile)}")
        print(" Resource Production This Turn:")
        for name, amt in production_named.items():
            print(f"   +{amt} {name}")
        print(" Resource Stockpile:")
        for name, amt in stockpile:
            print(f"   {name}: {amt}")
        print(f" Income: Tax {int(tax_income)} | Buildings {int(building_income)}")
        print(f" Expenses: Admin {int(administration_cost)} | Military {int(military_upkeep)} | Buildings {int(building_upkeep)}")
        print(f" Treasury: {treasury} (unchanged)")

    conn.commit()
    conn.close()
    print("\n✅ IMPORT ECONOMY COMPLETE\n")

if __name__ == "__main__":
    import_economy()