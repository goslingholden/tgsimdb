import csv
import configparser
import math
import os
import sys
from db_utils import get_connection
from economy_tick import (
    FOOD_PER_1000_POP,
    FOOD_RESOURCE_NAMES,
    FOOD_SHORTAGE_TAX_PENALTY_MAX,
    calculate_political_modifiers,
    get_additive_modifier,
    get_country_modifier,
    get_building_country_modifier,
    get_building_effect_total,
    get_country_tax_base,
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
    get_resource_cap,
    get_resource_ids_by_name,
    get_land_unit_cap,
    get_navy_unit_cap,
)


config = configparser.ConfigParser()
config.read("config.ini")

BASE_TAX_PER_POP = float(config["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = float(config["economy"]["admin_cost_per_province"])
DATA_ROOT = "data"


def resolve_data_dir(scenario_name=None):
    if scenario_name:
        data_dir = os.path.join(DATA_ROOT, scenario_name)
    else:
        data_dir = DATA_ROOT

    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    return data_dir


def data_file(data_dir, filename):
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required data file not found: {path}")
    return path


def import_cultures(cursor, data_dir):
    with open(data_file(data_dir, "cultures.csv"), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO cultures (culture, culture_group)
                VALUES (?, ?)
                ON CONFLICT(culture) DO UPDATE SET
                    culture_group = excluded.culture_group
            """, (
                row["culture"],
                row["culture_group"],
            ))


def import_countries(cursor, data_dir):
    with open(data_file(data_dir, "countries.csv"), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO countries (code, name, capital, culture,
                    religion, government, stability,
                    unrest, corruption, at_war, war_exhaustion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    capital = excluded.capital,
                    culture = excluded.culture,
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
                row.get("religion", "Unknown"),
                row.get("government", "Unknown"),
                int(row.get("stability", 50)),
                int(row.get("unrest", 0)),
                float(row.get("corruption", 0.0)),
                int(row.get("at_war", 0)),
                int(row.get("war_exhaustion", 0))
            ))


def import_provinces(cursor, data_dir):
    with open(data_file(data_dir, "provinces.csv"), newline="", encoding="utf-8") as f:
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


def import_building_types(cursor, data_dir):
    with open(data_file(data_dir, "building_types.csv"), newline="", encoding="utf-8") as f:
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


def import_province_buildings(cursor, data_dir):
    with open(data_file(data_dir, "province_buildings.csv"), newline="", encoding="utf-8") as f:
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


def import_country_economy(cursor, data_dir):
    with open(data_file(data_dir, "country_economy.csv"), newline="", encoding="utf-8") as f:
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


def import_unit_types(cursor, data_dir):
    with open(data_file(data_dir, "unit_types.csv"), newline="", encoding="utf-8") as f:
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


def import_country_units(cursor, data_dir):
    with open(data_file(data_dir, "country_units.csv"), newline="", encoding="utf-8") as f:
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


def import_modifiers(cursor, data_dir):
    with open(data_file(data_dir, "modifiers.csv"), newline="", encoding="utf-8") as f:
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


def import_building_effects(cursor, data_dir):
    with open(data_file(data_dir, "building_effects.csv"), newline="", encoding="utf-8") as f:
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


def import_country_modifiers(cursor, data_dir):
    with open(data_file(data_dir, "country_modifiers.csv"), newline="", encoding="utf-8") as f:
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


def import_resources(cursor, data_dir):
    with open(data_file(data_dir, "resources.csv"), newline="", encoding="utf-8") as f:
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


def import_building_resource_costs(cursor, data_dir):
    with open(data_file(data_dir, "building_resource_cost.csv"), newline="", encoding="utf-8") as f:
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



def import_unit_resource_costs(cursor, data_dir):
    with open(data_file(data_dir, "unit_resource_costs.csv"), newline="", encoding="utf-8") as f:
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
        "cultures", "countries", "provinces", "country_economy",
        "building_types", "province_buildings", "building_effects",
        "country_modifiers", "unit_types", "country_units",
        "resources", "country_resources",
        "building_resource_costs", "unit_resource_costs",
        "event_log"
    ]

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cursor.fetchall()}

    missing = [t for t in required_tables if t not in existing]
    if missing:
        raise RuntimeError(f"Missing required tables: {missing}")


def get_country_resource_production_snapshot(cursor, country):
    production = get_resource_production(cursor, country)
    additive_resource_effects = {
        "livestock": get_building_effect_total(cursor, country, "prod_livestock"),
        "grain": get_building_effect_total(cursor, country, "prod_grain"),
        "slaves": get_building_effect_total(cursor, country, "prod_slaves"),
        "base_metals": get_building_effect_total(cursor, country, "prod_base_metals"),
        "iron": get_building_effect_total(cursor, country, "prod_iron"),
        "stone": get_building_effect_total(cursor, country, "prod_stone"),
        "wood": get_building_effect_total(cursor, country, "prod_wood"),
        "cloth": get_building_effect_total(cursor, country, "prod_cloth"),
        "wine": get_building_effect_total(cursor, country, "prod_wine"),
        "honey": get_building_effect_total(cursor, country, "prod_honey"),
        "olives": get_building_effect_total(cursor, country, "prod_olives"),
    }
    additive_resource_ids = {
        name: resource_ids[0]
        for name, resource_ids in (
            (resource_name, get_resource_ids_by_name(cursor, [resource_name]))
            for resource_name in additive_resource_effects
        )
        if resource_ids
    }

    for resource_name, bonus_amount in additive_resource_effects.items():
        resource_id = additive_resource_ids.get(resource_name)
        if resource_id and bonus_amount > 0:
            production[resource_id] = production.get(resource_id, 0) + int(bonus_amount)

    return production


def get_food_tax_multiplier_preview(cursor, country, population):
    raw_required_food = (population / 1000) * FOOD_PER_1000_POP
    required_food = max(0, int(math.floor(raw_required_food + 0.5)))
    if required_food == 0:
        return 1.0

    food_resource_ids = get_resource_ids_by_name(cursor, FOOD_RESOURCE_NAMES)
    if not food_resource_ids:
        return 1.0

    placeholders = ",".join("?" for _ in food_resource_ids)
    cursor.execute(
        f"""
        SELECT COALESCE(SUM(stockpile), 0)
        FROM country_resources
        WHERE country_code = ?
          AND resource_id IN ({placeholders})
        """,
        (country, *food_resource_ids)
    )
    available_food = int(cursor.fetchone()[0] or 0)
    shortage = max(0, required_food - available_food)
    shortage_ratio = shortage / required_food if required_food > 0 else 0.0
    return max(0.0, 1.0 - (shortage_ratio * FOOD_SHORTAGE_TAX_PENALTY_MAX))


def refresh_country_economy(cursor, country, seed_resource_stockpiles=False, verbose=False):
    cursor.execute("SELECT treasury, tax_rate FROM country_economy WHERE country_code = ?", (country,))
    row = cursor.fetchone()
    if not row:
        if verbose:
            print(f"⚠ No economy row for {country}")
        return None

    treasury, tax_rate = row
    population = get_population(cursor, country)
    provinces = get_province_count(cursor, country)
    political_mods = calculate_political_modifiers(cursor, country)
    if not political_mods:
        return None

    tax_eff = get_country_modifier(cursor, country, "tax_efficiency")
    tax_eff *= get_building_country_modifier(cursor, country, "tax_efficiency")
    tax_eff *= political_mods["tax_efficiency_mod"]

    admin_mod = get_country_modifier(cursor, country, "admin_cost_modifier")
    admin_mod *= get_building_country_modifier(cursor, country, "admin_cost_modifier")
    admin_eff = get_country_modifier(cursor, country, "admin_efficiency")
    admin_eff *= get_building_country_modifier(cursor, country, "admin_efficiency")
    admin_mod /= max(0.0001, admin_eff)
    admin_mod *= political_mods["admin_cost_mod"]

    upkeep_mod = get_country_modifier(cursor, country, "military_upkeep_modifier")
    upkeep_mod *= political_mods["military_upkeep_mod"]

    building_income_mult = get_country_modifier(cursor, country, "production_efficiency")
    building_income_mult *= get_building_country_modifier(cursor, country, "production_efficiency")

    base_tax = get_country_tax_base(cursor, country)
    tax_income = base_tax * tax_rate * tax_eff
    tax_income *= (1 - political_mods["corruption"] * 0.5)
    tax_income *= get_food_tax_multiplier_preview(cursor, country, population)

    administration_cost = provinces * ADMIN_COST_PER_PROVINCE * admin_mod
    military_upkeep = get_military_upkeep(cursor, country) * upkeep_mod
    building_income_raw, building_upkeep = get_building_economy(cursor, country)
    building_income = building_income_raw * building_income_mult

    base_growth = float(config["politics"]["base_economic_growth"])
    growth_stability = (
        (political_mods["stability"] - 50)
        * float(config["politics"]["economic_growth_stability_factor"])
    )
    growth_unrest = -political_mods["unrest"] * float(config["politics"]["economic_growth_unrest_factor"])
    growth_corruption = -political_mods["corruption"] * float(config["politics"]["economic_growth_corruption_factor"])
    growth_war = float(config["politics"]["growth_war_factor"]) if political_mods["at_war"] else 0
    growth_buildings = building_income_raw * float(config["politics"]["growth_building_factor"])
    growth_modifier_bonus = get_additive_modifier(cursor, country, "economic_growth")
    total_growth_rate = max(
        0.0,
        base_growth + growth_stability + growth_unrest + growth_corruption
        + growth_war + growth_buildings + growth_modifier_bonus
    )
    productive_income_base = max(0, tax_income + building_income)
    growth_amount = int(productive_income_base * total_growth_rate)

    total_income = int(tax_income + building_income + growth_amount)
    total_expenses = int(administration_cost + military_upkeep + building_upkeep)
    production = get_country_resource_production_snapshot(cursor, country)

    if seed_resource_stockpiles:
        cursor.execute("UPDATE country_resources SET stockpile = 0 WHERE country_code = ?", (country,))
        for resource_id, amount in production.items():
            cursor.execute("""
                UPDATE country_resources
                SET stockpile = ?
                WHERE country_code = ? AND resource_id = ?
            """, (int(amount), country, resource_id))

    cursor.execute("""
        UPDATE country_economy SET
            tax_income = ?,
            building_income = ?,
            total_income = ?,
            administration_cost = ?,
            military_upkeep = ?,
            building_upkeep = ?,
            total_expenses = ?,
            economic_growth = ?,
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
        total_growth_rate,
        population,
        country
    ))

    resource_cap = get_resource_cap(cursor, country)
    stockpile_total = cursor.execute(
        "SELECT COALESCE(SUM(stockpile), 0) FROM country_resources WHERE country_code = ?",
        (country,)
    ).fetchone()[0] or 0

    result = {
        "country": country,
        "treasury": treasury,
        "tax_rate": tax_rate,
        "population": population,
        "provinces": provinces,
        "tax_income": int(tax_income),
        "building_income": int(building_income),
        "total_income": total_income,
        "administration_cost": int(administration_cost),
        "military_upkeep": int(military_upkeep),
        "building_upkeep": int(building_upkeep),
        "total_expenses": total_expenses,
        "economic_growth": total_growth_rate,
        "resource_cap": resource_cap,
        "stockpile_total": stockpile_total,
        "production": production,
        "land_unit_cap": get_land_unit_cap(cursor, country),
        "navy_unit_cap": get_navy_unit_cap(cursor, country),
        "total_land_units": get_total_land_units(cursor, country),
        "total_navy_units": get_total_navy_units(cursor, country),
        "coastal_provinces": get_coastal_province_count(cursor, country),
        "land_military_upkeep": int(get_land_military_upkeep(cursor, country) * upkeep_mod),
        "navy_military_upkeep": int(
            get_navy_upkeep(cursor, country)
            * get_country_modifier(cursor, country, "navy_upkeep_modifier")
            * political_mods["military_upkeep_mod"]
        ),
    }

    if verbose:
        cursor.execute("SELECT id, name FROM resources")
        resource_names = {row[0]: row[1] for row in cursor.fetchall()}
        if production:
            resource_display = ", ".join(
                f"{resource_names.get(resource_id, f'ID_{resource_id}')}: {amount}"
                for resource_id, amount in sorted(production.items())
            )
        else:
            resource_display = "None"

        print(
            f"\n=== {country} DEBUG INFO ==="
            f"\nPopulation: {population:,} (provinces: {provinces})"
            f"\nLand Units: {result['total_land_units']:,}/{result['land_unit_cap']:,}"
            f"\nNavy Units: {result['total_navy_units']:,}/{result['navy_unit_cap']:,} "
            f"(coastal: {result['coastal_provinces']})"
            f"\nTax Income: {result['tax_income']:,}"
            f"\nBuilding Income: {result['building_income']:,}"
            f"\nTotal Income: {total_income:,}"
            f"\nAdministration Cost: {result['administration_cost']:,}"
            f"\nLand Military Upkeep: {result['land_military_upkeep']:,}"
            f"\nNavy Military Upkeep: {result['navy_military_upkeep']:,}"
            f"\nBuilding Upkeep: {result['building_upkeep']:,}"
            f"\nTotal Expenses: {total_expenses:,}"
            f"\nTreasury: {treasury:,}"
            f"\nResource Cap: {resource_cap:,} | Total Stockpile: {stockpile_total:,}"
            f"\nResource Production: {resource_display}"
            f"\n--------------------------------------------------"
        )

    return result


def refresh_all_country_economies(cursor, seed_resource_stockpiles=False, verbose=False):
    validate_schema(cursor)
    ensure_country_resource_rows(cursor)
    cursor.execute("SELECT code FROM countries ORDER BY code")
    countries = [row[0] for row in cursor.fetchall()]
    return [
        result
        for result in (
            refresh_country_economy(cursor, country, seed_resource_stockpiles=seed_resource_stockpiles, verbose=verbose)
            for country in countries
        )
        if result is not None
    ]


def import_economy_snapshot(cursor):
    print("\n=== IMPORT ECONOMY START ===")
    refresh_all_country_economies(cursor, seed_resource_stockpiles=True, verbose=True)
    print("✅ IMPORT ECONOMY COMPLETE")


def main():
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else None
    data_dir = resolve_data_dir(scenario_name)
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        import_resources(cursor, data_dir)
        import_cultures(cursor, data_dir)
        import_countries(cursor, data_dir)
        import_provinces(cursor, data_dir)
        import_building_types(cursor, data_dir)
        import_building_resource_costs(cursor, data_dir)
        import_province_buildings(cursor, data_dir)
        import_country_economy(cursor, data_dir)
        import_unit_types(cursor, data_dir)
        import_unit_resource_costs(cursor, data_dir)
        import_country_units(cursor, data_dir)
        import_modifiers(cursor, data_dir)
        import_building_effects(cursor, data_dir)
        import_country_modifiers(cursor, data_dir)
        import_economy_snapshot(cursor)

        conn.commit()
        print(f"🌍 World data and economy snapshot imported successfully from {data_dir}.")

    except Exception as e:
        conn.rollback()
        print("❌ Import failed. All changes have been rolled back.")
        print("ERROR:", e)
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    main()
