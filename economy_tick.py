import json
from db_utils import get_connection

# ---------------- LOAD CONFIG ----------------
with open("config.json", "r") as f:
    CONFIG = json.load(f)

BASE_TAX_PER_POP = CONFIG["economy"]["base_tax_per_pop"]
BASE_ADMIN_COST_PER_PROVINCE = CONFIG["economy"]["admin_cost_per_province"]
MILITARY_UPKEEP_PER_POP = CONFIG["economy"]["military_upkeep_per_pop"]
# -------------------------------------------


def get_countries(cursor):
    cursor.execute("SELECT code FROM countries;")
    return [row[0] for row in cursor.fetchall()]


def get_country_population(cursor, country_code):
    cursor.execute("""
        SELECT SUM(population) 
        FROM provinces 
        WHERE owner_country_code = ?;
    """, (country_code,))
    return cursor.fetchone()[0] or 0


def get_province_count(cursor, country_code):
    cursor.execute("""
        SELECT COUNT(*) 
        FROM provinces 
        WHERE owner_country_code = ?;
    """, (country_code,))
    return cursor.fetchone()[0] or 0


def economy_tick():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    countries = get_countries(cursor)

    print("=== ECONOMY TICK START ===")

    for country in countries:
        # Fetch economy data
        cursor.execute("""
            SELECT treasury, tax_rate, tax_efficiency, corruption
            FROM country_economy
            WHERE country_code = ?;
        """, (country,))
        row = cursor.fetchone()

        if not row:
            print(f"⚠ No economy entry for {country}")
            continue

        treasury, tax_rate, tax_efficiency, corruption = row

        # Get demographic data
        population = get_country_population(cursor, country)
        province_count = get_province_count(cursor, country)

        # ---------------- TAX INCOME ----------------
        base_tax = population * BASE_TAX_PER_POP
        tax_income = base_tax * tax_rate * tax_efficiency * (1 - corruption)

        # ---------------- ADMIN COST ----------------
        administration_cost = province_count * BASE_ADMIN_COST_PER_PROVINCE

        # ---------------- MILITARY UPKEEP ----------------
        military_upkeep = population * MILITARY_UPKEEP_PER_POP

        # ---------------- TOTALS ----------------
        total_income = int(tax_income)
        total_expenses = int(administration_cost + military_upkeep)
        new_treasury = treasury + total_income - total_expenses

        # Update database
        cursor.execute("""
            UPDATE country_economy
            SET 
                treasury = ?,
                tax_income = ?,
                total_income = ?,
                administration_cost = ?,
                military_upkeep = ?,
                total_expenses = ?,
                total_population = ?
            WHERE country_code = ?;
        """, (
            new_treasury,
            int(tax_income),
            total_income,
            administration_cost,
            int(military_upkeep),
            total_expenses,
            population,
            country
        ))

        # Console report
        print(f"{country} | Pop: {population} | Provinces: {province_count}")
        print(f"  Income: {total_income} (Tax)")
        print(f"  Expenses: {total_expenses} (Admin: {administration_cost}, Military: {int(military_upkeep)})")
        print(f"  Treasury: {treasury} → {new_treasury}")
        print("--------------------------------------------------")

    conn.commit()
    conn.close()
    print("✅ ECONOMY TICK COMPLETE")


if __name__ == "__main__":
    economy_tick()