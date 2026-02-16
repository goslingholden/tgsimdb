from db_utils import get_connection
import configparser

# LOAD CONFIG
config_file = configparser.ConfigParser()
config_file.read("config.ini")

BASE_TAX_PER_POP = float(config_file["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = int(config_file["economy"]["admin_cost_per_province"])

POP_PER_UNIT = int(config_file["military"]["pop_per_unit"])
UNIT_LIMIT_PERCENT = float(config_file["military"]["unit_limit_percent"])
OVER_LIMIT_UPKEEP_MULTIPLIER = float(config_file["military"]["over_limit_upkeep_multiplier"])


# ---------------- HELPERS ----------------
def get_countries(cursor):
    cursor.execute("SELECT code FROM countries;")
    return [row[0] for row in cursor.fetchall()]


def get_country_population(cursor, country_code):
    cursor.execute("SELECT SUM(population) FROM provinces WHERE owner_country_code=?;", (country_code,))
    return cursor.fetchone()[0] or 0


def get_province_count(cursor, country_code):
    cursor.execute("SELECT COUNT(*) FROM provinces WHERE owner_country_code=?;", (country_code,))
    return cursor.fetchone()[0] or 0


def get_military_data(cursor, country_code):
    cursor.execute("""
        SELECT SUM(cu.amount), SUM(cu.amount * ut.upkeep_cost)
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ?;
    """, (country_code,))
    return cursor.fetchone() or (0, 0)


# ---------------- MAIN TICK ----------------
def economy_tick():
    conn = get_connection()
    cursor = conn.cursor()
    countries = get_countries(cursor)

    print("\n=== 💰 ECONOMY TICK START ===\n")

    for country in countries:
        cursor.execute("""
            SELECT treasury, tax_rate, tax_efficiency, corruption
            FROM country_economy WHERE country_code=?;
        """, (country,))
        row = cursor.fetchone()
        if not row:
            continue

        treasury, tax_rate, tax_efficiency, corruption = row
        population = get_country_population(cursor, country)
        provinces = get_province_count(cursor, country)
        units, base_upkeep = get_military_data(cursor, country)

        # TAX
        tax_income = population * BASE_TAX_PER_POP * tax_rate * tax_efficiency * (1 - corruption)

        # ADMIN
        admin_cost = provinces * ADMIN_COST_PER_PROVINCE

        # UNIT LIMIT
        unit_limit = int((population * UNIT_LIMIT_PERCENT) / POP_PER_UNIT)
        over = max(0, units - unit_limit)
        military_upkeep = base_upkeep

        if over > 0:
            penalty = over * (base_upkeep / max(units, 1)) * (OVER_LIMIT_UPKEEP_MULTIPLIER - 1)
            military_upkeep += penalty

        total_income = int(tax_income)
        total_expenses = int(admin_cost + military_upkeep)
        new_treasury = treasury + total_income - total_expenses

        cursor.execute("""
            UPDATE country_economy
            SET treasury=?, military_upkeep=?, administration_cost=?, total_population=?
            WHERE country_code=?;
        """, (new_treasury, int(military_upkeep), admin_cost, population, country))

        print(f"{country}: Pop {population}, Units {units}/{unit_limit}, Treasury {treasury}->{new_treasury}")

    conn.commit()
    conn.close()
    print("\n✅ ECONOMY TICK COMPLETE\n")


if __name__ == "__main__":
    economy_tick()