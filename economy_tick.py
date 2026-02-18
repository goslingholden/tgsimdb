from db_utils import get_connection
import configparser

# ---------------- LOAD CONFIG ----------------
config = configparser.ConfigParser()
config.read("config.ini")

BASE_TAX_PER_POP = float(config["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = float(config["economy"]["admin_cost_per_province"])

RESOURCE_PRODUCTION = int(config["resources"]["resource_production"])
RESOURCE_CAP_PER_PROVINCE = int(config["resources"]["resource_cap_per_province"])

POP_PER_UNIT = int(config["military"]["pop_per_unit"])
BASE_UNIT_RATIO = float(config["military"]["base_unit_ratio"])

# --------------------------------------------


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


# ================== MODIFIER SYSTEM ==================

def get_country_modifier(cursor, country, key):
    cursor.execute("SELECT default_value FROM modifiers WHERE modifier_key = ?", (key,))
    base = cursor.fetchone()
    base_value = base[0] if base else 1.0

    cursor.execute("""
        SELECT value FROM country_modifiers 
        WHERE country_code = ? AND modifier_key = ?
    """, (country, key))
    row = cursor.fetchone()
    country_value = row[0] if row else 0.0

    return base_value * (1 + country_value)


def get_building_country_modifier(cursor, country, key):
    cursor.execute("""
        SELECT COALESCE(SUM(be.value * pb.amount), 0)
        FROM province_buildings pb
        JOIN building_effects be ON pb.building_type_id = be.building_type_id
        JOIN provinces p ON pb.province_id = p.id
        WHERE p.owner_country_code = ?
        AND be.scope = 'country'
        AND be.modifier_key = ?
    """, (country, key))

    return 1 + (cursor.fetchone()[0] or 0.0)


# ================== DEMOGRAPHICS ==================

def get_population(cursor, country):
    cursor.execute("SELECT SUM(population) FROM provinces WHERE owner_country_code = ?", (country,))
    return cursor.fetchone()[0] or 0


def get_province_count(cursor, country):
    cursor.execute("SELECT COUNT(*) FROM provinces WHERE owner_country_code = ?", (country,))
    return cursor.fetchone()[0] or 0


# ================== MILITARY ==================

def get_military_upkeep(cursor, country):
    cursor.execute("""
        SELECT COALESCE(SUM(cu.amount * ut.upkeep_cost), 0)
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ?
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_total_units(cursor, country):
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM country_units WHERE country_code = ?", (country,))
    return cursor.fetchone()[0] or 0


# ================== BUILDING ECONOMY ==================

def get_building_economy(cursor, country):
    cursor.execute("""
        SELECT 
            COALESCE(SUM(bt.base_tax_income * pb.amount), 0),
            COALESCE(SUM(bt.base_upkeep * pb.amount), 0)
        FROM province_buildings pb
        JOIN building_types bt ON pb.building_type_id = bt.id
        JOIN provinces p ON pb.province_id = p.id
        WHERE p.owner_country_code = ?
    """, (country,))

    income, upkeep = cursor.fetchone()
    return income or 0, upkeep or 0


# ================= RESOURCE SYSTEM =================

def get_resource_names(cursor):
    cursor.execute("SELECT id, name FROM resources")
    return {rid: name for rid, name in cursor.fetchall()}


def get_resource_production(cursor, country):
    cursor.execute("""
        SELECT resource_id, COUNT(*) 
        FROM provinces
        WHERE owner_country_code = ?
        AND resource_id IS NOT NULL
        GROUP BY resource_id
    """, (country,))

    return {rid: count * RESOURCE_PRODUCTION for rid, count in cursor.fetchall()}


def get_country_stockpile(cursor, country):
    cursor.execute("""
        SELECT r.name, cr.stockpile
        FROM country_resources cr
        JOIN resources r ON cr.resource_id = r.id
        WHERE cr.country_code = ?
        ORDER BY r.name
    """, (country,))
    return cursor.fetchall()


# ================== ECONOMY TICK ==================

def economy_tick():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    validate_schema(cursor)

    cursor.execute("SELECT code FROM countries")
    countries = [c[0] for c in cursor.fetchall()]

    resource_names = get_resource_names(cursor)

    print("\n=== ECONOMY TICK START ===")

    for country in countries:

        cursor.execute("""
            SELECT treasury, tax_rate
            FROM country_economy
            WHERE country_code = ?
        """, (country,))
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
        total_units = get_total_units(cursor, country)

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

        # Enforce total shared cap
        cursor.execute("""
            SELECT SUM(stockpile) FROM country_resources WHERE country_code = ?
        """, (country,))
        total_stockpile = cursor.fetchone()[0] or 0

        if total_stockpile > resource_cap:
            excess = total_stockpile - resource_cap
            cursor.execute("""
                UPDATE country_resources
                SET stockpile = stockpile - (
                    stockpile * 1.0 / (SELECT SUM(stockpile) FROM country_resources WHERE country_code = ?)
                ) * ?
                WHERE country_code = ?
            """, (country, excess, country))

        # ----- TOTALS -----
        total_income = int(tax_income + building_income)
        total_expenses = int(administration_cost + military_upkeep + building_upkeep)
        new_treasury = treasury + total_income - total_expenses

        # SAVE
        cursor.execute("""
            UPDATE country_economy SET
                treasury = ?,
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
            new_treasury,
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
        stockpile = get_country_stockpile(cursor, country)
        cursor.execute("SELECT SUM(stockpile) FROM country_resources WHERE country_code = ?", (country,))
        total_stockpile = cursor.fetchone()[0] or 0

        print(f"\n{country}")
        print(f" Population: {population} | Provinces: {provinces}")
        print(f" Tax Eff x{tax_eff:.3f} | Admin Mod x{admin_mod:.3f}")
        print(f" Buildings Raw: Income {building_income_raw}, Upkeep {building_upkeep}")
        print(f" Unit Limit: {total_units}/{unit_limit}")

        print(f" Resource Cap: {resource_cap} | Total Stockpile: {int(total_stockpile)}")
        print(" Resource Production This Turn:")
        for name, amt in production_named.items():
            print(f"   +{amt} {name}")

        print(" Resource Stockpile:")
        for name, amt in stockpile:
            print(f"   {name}: {int(amt)}")

        print(f" Income: Tax {int(tax_income)} | Buildings {int(building_income)}")
        print(f" Expenses: Admin {int(administration_cost)} | Military {int(military_upkeep)} | Buildings {int(building_upkeep)}")
        print(f" Treasury: {treasury} → {new_treasury}")
        print("--------------------------------------------------")

    conn.commit()
    conn.close()
    print("\n✅ ECONOMY TICK COMPLETE\n")


if __name__ == "__main__":
    economy_tick()
