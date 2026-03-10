from db_utils import get_connection
import configparser
import math

# ---------------- LOAD CONFIG ----------------
config = configparser.ConfigParser()
config.read("config.ini")

BASE_TAX_PER_POP = float(config["economy"]["base_tax_per_pop"])
ADMIN_COST_PER_PROVINCE = float(config["economy"]["admin_cost_per_province"])

RESOURCE_PRODUCTION = int(config["resources"]["resource_production"])
RESOURCE_CAP_PER_PROVINCE = int(config["resources"]["resource_cap_per_province"])

FOOD_PER_1000_POP = float(config["food"]["food_per_1000_pop"])
FOOD_RESOURCE_NAMES = [name.strip() for name in config["food"]["food_resource_names"].split(",") if name.strip()]
FOOD_SHORTAGE_TAX_PENALTY_MAX = float(config["food"]["food_shortage_tax_penalty_max"])
FOOD_SHORTAGE_UNREST_INCREASE_MAX = float(config["food"]["food_shortage_unrest_increase_max"])

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

def validate_political_data(cursor):
    """Validate political values are within bounds."""
    
    cursor.execute("""
        SELECT code, stability, unrest, corruption, war_exhaustion
        FROM countries
        WHERE stability NOT BETWEEN 0 AND 100
           OR unrest NOT BETWEEN 0 AND 100
           OR corruption NOT BETWEEN 0.0 AND 1.0
           OR war_exhaustion NOT BETWEEN 0 AND 100
    """)
    
    invalid = cursor.fetchall()
    if invalid:
        print("❌ Invalid political values found:")
        for row in invalid:
            print(f"  {row[0]}: stability={row[1]}, unrest={row[2]}, corruption={row[3]}, war_exhaustion={row[4]}")
        return False
    return True

# ================ POLITICAL MODIFIERS ================
def calculate_political_modifiers(cursor, country_code):
    """Calculate all political modifiers for a country."""
    
    cursor.execute("""
        SELECT stability, unrest, corruption, at_war, war_exhaustion
        FROM countries WHERE code = ?
    """, (country_code,))
    row = cursor.fetchone()
    
    if not row:
        return None
    
    stability, unrest, corruption, at_war, war_exhaustion = row
    
    # Load config
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    # Calculate modifiers
    tax_efficiency_mod = 1.0
    admin_cost_mod = 1.0
    military_upkeep_mod = 1.0
    unrest_change = 0.0
    stability_change = 0.0
    corruption_change = 0.0
    war_exhaustion_change = 0.0
    population_change = 0
    
    # Load bounds from config
    tax_eff_min = float(config["bounds"]["tax_efficiency_min"])
    
    # Stability effects
    tax_efficiency_mod += (stability - 50) * 0.002
    unrest_change += (50 - stability) * 0.1
    
    # Unrest effects
    admin_cost_mod += unrest * float(config["politics"]["unrest_admin_multiplier"])
    tax_efficiency_mod -= unrest * float(config["politics"]["unrest_tax_penalty"])
    tax_efficiency_mod = max(tax_eff_min, tax_efficiency_mod)  # Cap minimum from config
    stability_change -= unrest * float(config["politics"]["unrest_stability_drain"])
    
    unrest_high_threshold = float(config["politics"]["unrest_high_threshold"])
    if unrest > unrest_high_threshold:
        pop_loss = int((unrest - unrest_high_threshold) * float(config["politics"]["unrest_population_loss_factor"]))
        population_change -= pop_loss
    
    # Corruption effects
    corruption_change = -corruption * 0.01  # Natural decay
    if at_war:
        corruption_change += float(config["politics"]["corruption_war_increase"])
    
    # War effects
    if at_war:
        military_upkeep_mod *= float(config["politics"]["war_military_upkeep_multiplier"])
        admin_cost_mod += float(config["politics"]["war_admin_cost_multiplier"])
        war_exhaustion_change += float(config["politics"]["war_exhaustion_per_turn"])
        tax_efficiency_mod -= war_exhaustion * 0.001
        unrest_change += war_exhaustion * 0.1
        stability_change -= war_exhaustion * 0.05
        military_upkeep_mod *= (1 + war_exhaustion * 0.003)
    
    # War exhaustion effects (applied even if not at war)
    if war_exhaustion > 0 and not at_war:
        tax_efficiency_mod -= war_exhaustion * 0.001
        unrest_change += war_exhaustion * 0.1
        stability_change -= war_exhaustion * 0.05
    
    return {
        'tax_efficiency_mod': max(tax_eff_min, tax_efficiency_mod),
        'admin_cost_mod': admin_cost_mod,
        'military_upkeep_mod': military_upkeep_mod,
        'unrest_change': unrest_change,
        'stability_change': stability_change,
        'corruption_change': corruption_change,
        'war_exhaustion_change': war_exhaustion_change,
        'population_change': population_change,
        # Include raw values for calculations and debugging
        'stability': stability,
        'unrest': unrest,
        'corruption': corruption,
        'at_war': at_war,
        'war_exhaustion': war_exhaustion
    }

def calculate_population_growth(population, stability, unrest, corruption):
    """Calculate natural population growth based on stability, unrest, corruption."""
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    base_growth_rate = float(config["population"]["base_growth_rate"])
    stability_factor = float(config["population"]["stability_growth_factor"])
    unrest_factor = float(config["population"]["unrest_growth_factor"])
    corruption_factor = float(config["population"]["corruption_growth_factor"])

    stability_bonus = (stability - 50) * stability_factor
    unrest_penalty = -unrest * unrest_factor
    corruption_penalty = -corruption * corruption_factor
    
    total_growth_rate = base_growth_rate + stability_bonus + unrest_penalty + corruption_penalty
    total_growth_rate = max(0.0, total_growth_rate)
    
    growth_amount = int(population * total_growth_rate)
    return growth_amount, total_growth_rate

def update_province_populations(cursor, country_code, net_pop_change):
    """Update population in all provinces of a country by distributing net change proportionally."""
    if net_pop_change == 0:
        return
    
    cursor.execute("SELECT id, population FROM provinces WHERE owner_country_code = ?", (country_code,))
    provinces = cursor.fetchall()
    if not provinces:
        return
    
    total_current_pop = sum(p[1] for p in provinces)
    if total_current_pop == 0:
        return
    
    # Distribute proportionally with rounding
    remaining = net_pop_change
    for i, (province_id, pop) in enumerate(provinces):
        if i == len(provinces) - 1:
            # Last province gets whatever remains to ensure total matches
            pop_change = remaining
        else:
            share = pop / total_current_pop
            pop_change = int(net_pop_change * share)
        new_pop = max(0, pop + pop_change)
        cursor.execute("UPDATE provinces SET population = ? WHERE id = ?", (new_pop, province_id))
        remaining -= pop_change

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
        AND be.scope IN ('country', 'province')
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

def get_navy_upkeep(cursor, country):
    """Get upkeep cost for navy units only."""
    cursor.execute("""
        SELECT COALESCE(SUM(cu.amount * ut.upkeep_cost), 0)
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ? AND ut.unit_category = 'naval'
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_land_military_upkeep(cursor, country):
    """Get upkeep cost for land military units only."""
    cursor.execute("""
        SELECT COALESCE(SUM(cu.amount * ut.upkeep_cost), 0)
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ? AND ut.unit_category = 'land'
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_military_upkeep(cursor, country):
    """Get total military upkeep (land units only, for backward compatibility)."""
    return get_land_military_upkeep(cursor, country)


def get_total_land_units(cursor, country):
    """Get total count of land military units (excluding navy)."""
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) 
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ? AND ut.unit_category = 'land'
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_total_navy_units(cursor, country):
    """Get total count of navy units."""
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) 
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ? AND ut.unit_category = 'naval'
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_coastal_province_count(cursor, country):
    """Get count of coastal provinces (is_naval = 1)."""
    cursor.execute("""
        SELECT COUNT(*) 
        FROM provinces 
        WHERE owner_country_code = ? AND is_naval = 1
    """, (country,))
    return cursor.fetchone()[0] or 0


def get_navy_unit_cap(cursor, country, coastal_multiplier=10):
    """
    Calculate navy unit cap based on coastal provinces.
    
    Args:
        cursor: DB cursor
        country: Country code
        coastal_multiplier: Base units per coastal province
    
    Returns:
        Maximum allowed navy units for this country
    """
    coastal_count = get_coastal_province_count(cursor, country)
    # Read from config if you want to make it configurable
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    # Default: 10 units per coastal province
    multiplier = int(config.get("military", "naval_cap_per_coastal_province", fallback=10))
    return coastal_count * multiplier

def validate_navy_cap(cursor, country):
    """Check if navy units exceed cap and return overage info."""
    current_navy = get_total_navy_units(cursor, country)
    navy_cap = get_navy_unit_cap(cursor, country)
    overage = max(0, current_navy - navy_cap)
    
    return {
        "current": current_navy,
        "cap": navy_cap,
        "is_over_cap": overage > 0,
        "overage": overage,
        "coastal_provinces": get_coastal_province_count(cursor, country)
    }


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

# =================== RESOURCES ===================
def get_resource_production(cursor, country):
    """Calculate resource production for a country.
    
    Returns a dictionary mapping produced resource_id to production amount.
    Production is based on owned provinces and each province contributes
    RESOURCE_PRODUCTION units of its own resource.
    """
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    production_per_resource = int(config["resources"]["resource_production"])

    cursor.execute("""
        SELECT p.resource_id, COUNT(*) AS province_count
        FROM provinces p
        WHERE p.owner_country_code = ?
          AND p.resource_id IS NOT NULL
        GROUP BY p.resource_id
    """, (country,))

    return {
        resource_id: province_count * production_per_resource
        for resource_id, province_count in cursor.fetchall()
    }


def ensure_country_resource_rows(cursor):
    """Ensure country_resources has one row per country/resource pair."""
    cursor.execute("""
        INSERT OR IGNORE INTO country_resources (country_code, resource_id, stockpile)
        SELECT c.code, r.id, 0
        FROM countries c
        CROSS JOIN resources r
    """)


def apply_resource_production(cursor, country, production, resource_cap):
    """Apply production to stockpile, respecting total cap per country."""
    cursor.execute("""
        SELECT COALESCE(SUM(stockpile), 0)
        FROM country_resources
        WHERE country_code = ?
    """, (country,))
    current_total = cursor.fetchone()[0] or 0
    remaining_capacity = max(0, resource_cap - current_total)

    actually_added = {}
    for resource_id, amount in sorted(production.items()):
        if remaining_capacity <= 0:
            actually_added[resource_id] = 0
            continue
        add_amount = min(amount, remaining_capacity)
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile + ?
            WHERE country_code = ? AND resource_id = ?
        """, (add_amount, country, resource_id))
        actually_added[resource_id] = add_amount
        remaining_capacity -= add_amount

    return actually_added


def get_resource_ids_by_name(cursor, resource_names):
    """Resolve resource names to ids, preserving requested order."""
    if not resource_names:
        return []
    placeholders = ",".join("?" for _ in resource_names)
    cursor.execute(
        f"SELECT id, name FROM resources WHERE name IN ({placeholders})",
        tuple(resource_names)
    )
    name_to_id = {name: rid for rid, name in cursor.fetchall()}
    return [name_to_id[name] for name in resource_names if name in name_to_id]


def consume_food_resources(cursor, country, population, food_resource_ids):
    """Consume food stockpiles for the year and return shortage metrics."""
    raw_required_food = (population / 1000) * FOOD_PER_1000_POP
    # Round halves up (not banker's rounding) to keep demand predictable.
    required_food = max(0, int(math.floor(raw_required_food + 0.5)))
    if required_food == 0 or not food_resource_ids:
        return {
            "required": required_food,
            "consumed": 0,
            "shortage": required_food,
            "shortage_ratio": 1.0 if required_food > 0 else 0.0,
            "consumed_by_resource": {}
        }

    placeholders = ",".join("?" for _ in food_resource_ids)
    cursor.execute(
        f"""
        SELECT resource_id, stockpile
        FROM country_resources
        WHERE country_code = ?
          AND resource_id IN ({placeholders})
        """,
        (country, *food_resource_ids)
    )
    stockpile_map = {resource_id: int(stockpile or 0) for resource_id, stockpile in cursor.fetchall()}

    remaining_need = required_food
    consumed_by_resource = {}

    # Consume in configured priority order
    for resource_id in food_resource_ids:
        stockpile = stockpile_map.get(resource_id, 0)
        if remaining_need <= 0:
            break
        consumed = min(stockpile, remaining_need)
        if consumed > 0:
            cursor.execute(
                """
                UPDATE country_resources
                SET stockpile = stockpile - ?
                WHERE country_code = ? AND resource_id = ?
                """,
                (consumed, country, resource_id)
            )
            consumed_by_resource[resource_id] = consumed
            remaining_need -= consumed

    consumed_total = required_food - remaining_need
    shortage = max(0, remaining_need)
    shortage_ratio = (shortage / required_food) if required_food > 0 else 0.0

    return {
        "required": required_food,
        "consumed": consumed_total,
        "shortage": shortage,
        "shortage_ratio": shortage_ratio,
        "consumed_by_resource": consumed_by_resource
    }

# ================== ECONOMY TICK ==================

def economy_tick():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    validate_schema(cursor)
    if not validate_political_data(cursor):
        conn.close()
        return
    # Keep resource stockpiles integer-only even if old runs introduced fractions.
    cursor.execute("UPDATE country_resources SET stockpile = CAST(stockpile AS INTEGER)")
    ensure_country_resource_rows(cursor)
    
    cursor.execute("SELECT code FROM countries")
    countries = [c[0] for c in cursor.fetchall()]
    resource_names = {rid: name for rid, name in cursor.execute("SELECT id, name FROM resources").fetchall()}
    food_resource_ids = get_resource_ids_by_name(cursor, FOOD_RESOURCE_NAMES)
    
    print("\n=== ECONOMY TICK START ===")
    
    for country in countries:
        # Get base economy data
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
        
        # Get population and provinces
        population = get_population(cursor, country)
        provinces = get_province_count(cursor, country)
        
        # Calculate political modifiers
        political_mods = calculate_political_modifiers(cursor, country)
        if not political_mods:
            continue
        
        # --- Apply population growth (add to population_change) ---
        pop_growth, pop_growth_rate = calculate_population_growth(
            population,
            political_mods['stability'],
            political_mods['unrest'],
            political_mods['corruption']
        )
        political_mods['population_change'] += pop_growth

        # --- Produce and consume resources before final economy math ---
        production = get_resource_production(cursor, country)
        resource_cap = provinces * RESOURCE_CAP_PER_PROVINCE
        actually_added = apply_resource_production(cursor, country, production, resource_cap)
        food_result = consume_food_resources(cursor, country, population, food_resource_ids)
        food_shortage_ratio = food_result["shortage_ratio"]
        food_tax_multiplier = max(0.0, 1.0 - (food_shortage_ratio * FOOD_SHORTAGE_TAX_PENALTY_MAX))
        food_unrest_increase = food_shortage_ratio * FOOD_SHORTAGE_UNREST_INCREASE_MAX
        political_mods['unrest_change'] += food_unrest_increase
        
        # --- Apply modifiers to existing calculations ---
        tax_eff = get_country_modifier(cursor, country, "tax_efficiency")
        tax_eff *= get_building_country_modifier(cursor, country, "tax_efficiency")
        tax_eff *= political_mods['tax_efficiency_mod']
        
        admin_mod = get_country_modifier(cursor, country, "admin_cost_modifier")
        admin_mod *= get_building_country_modifier(cursor, country, "admin_cost_modifier")
        # Higher admin_efficiency should reduce costs, not increase them.
        admin_eff = get_country_modifier(cursor, country, "admin_efficiency")
        admin_eff *= get_building_country_modifier(cursor, country, "admin_efficiency")
        admin_mod /= max(0.0001, admin_eff)
        admin_mod *= political_mods['admin_cost_mod']
        
        upkeep_mod = get_country_modifier(cursor, country, "military_upkeep_modifier")
        upkeep_mod *= political_mods['military_upkeep_mod']
        
        # Existing calculations
        base_tax = population * float(config["economy"]["base_tax_per_pop"])
        tax_income = base_tax * tax_rate * tax_eff
        
        # Apply corruption tax loss using raw corruption value
        tax_income_after_corruption = tax_income * (1 - political_mods['corruption'] * 0.5)
        tax_income_after_corruption *= food_tax_multiplier
        
        administration_cost = provinces * float(config["economy"]["admin_cost_per_province"]) * admin_mod
        
        land_upkeep = get_land_military_upkeep(cursor, country)
        navy_upkeep_raw = get_navy_upkeep(cursor, country)
        land_military_upkeep = land_upkeep * upkeep_mod
        navy_upkeep_mod = get_country_modifier(cursor, country, "navy_upkeep_modifier")
        navy_upkeep_mod *= political_mods['military_upkeep_mod']
        navy_military_upkeep = navy_upkeep_raw * navy_upkeep_mod
        military_upkeep = land_military_upkeep + navy_military_upkeep
        
        building_income_raw, building_upkeep = get_building_economy(cursor, country)
        building_income_mult = get_country_modifier(cursor, country, "production_efficiency")
        building_income_mult *= get_building_country_modifier(cursor, country, "production_efficiency")
        building_income = building_income_raw * building_income_mult
        
        # --- Economic growth calculation ---
        base_growth = float(config["politics"]["base_economic_growth"])
        growth_stability = (political_mods['stability'] - 50) * float(config["politics"]["economic_growth_stability_factor"])
        growth_unrest = -political_mods['unrest'] * float(config["politics"]["economic_growth_unrest_factor"])
        growth_corruption = -political_mods['corruption'] * float(config["politics"]["economic_growth_corruption_factor"])
        growth_war = float(config["politics"]["growth_war_factor"]) if political_mods['at_war'] else 0
        growth_buildings = building_income_raw * float(config["politics"]["growth_building_factor"])
        
        total_growth_rate = base_growth + growth_stability + growth_unrest + growth_corruption + growth_war + growth_buildings
        total_growth_rate = max(0.0, total_growth_rate)
        
        productive_income_base = max(0, tax_income_after_corruption + building_income)
        growth_amount = int(productive_income_base * total_growth_rate)
        
        # --- Calculate totals including growth as income ---
        total_income = int(tax_income_after_corruption + building_income + growth_amount)
        total_expenses = int(administration_cost + military_upkeep + building_upkeep)
        new_treasury = treasury + total_income - total_expenses
        
        # --- Compute new political values for display ---
        old_stability = political_mods['stability']
        old_unrest = political_mods['unrest']
        old_corruption = political_mods['corruption']
        old_war_exhaustion = political_mods['war_exhaustion']
        
        # Load bounds from config
        stability_min, stability_max = map(float, config["bounds"].get("stability_bounds", "0,100").split(','))
        unrest_min, unrest_max = map(float, config["bounds"].get("unrest_bounds", "0,100").split(','))
        corr_min, corr_max = map(float, config["bounds"]["corruption_bounds"].split(','))
        war_min, war_max = map(float, config["bounds"]["war_exhaustion_bounds"].split(','))
        
        new_stability = max(stability_min, min(stability_max, old_stability + political_mods['stability_change']))
        new_unrest = max(unrest_min, min(unrest_max, old_unrest + political_mods['unrest_change']))
        new_corruption = max(corr_min, min(corr_max, old_corruption + political_mods['corruption_change']))
        new_war_exhaustion = max(war_min, min(war_max, old_war_exhaustion + political_mods['war_exhaustion_change']))
        
        # --- Update province populations ---
        update_province_populations(cursor, country, political_mods['population_change'])
        
        # --- Update country economy ---
        cursor.execute("SELECT COALESCE(SUM(population), 0) FROM provinces WHERE owner_country_code = ?", (country,))
        new_total_population = cursor.fetchone()[0] or 0
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
                total_population = ?,
                economic_growth = ?
            WHERE country_code = ?
        """, (
            new_treasury,
            int(tax_income_after_corruption),
            int(building_income),
            total_income,
            int(administration_cost),
            int(military_upkeep),
            int(building_upkeep),
            total_expenses,
            new_total_population,
            total_growth_rate,
            country
        ))
        
        # --- Update political state ---
        cursor.execute("""
            UPDATE countries SET
                stability = ?,
                unrest = ?,
                corruption = ?,
                war_exhaustion = ?
            WHERE code = ?
        """, (new_stability, new_unrest, new_corruption, new_war_exhaustion, country))

        stockpile = cursor.execute("""
            SELECT r.name, cr.stockpile
            FROM country_resources cr
            JOIN resources r ON cr.resource_id = r.id
            WHERE cr.country_code = ?
            ORDER BY r.name
        """, (country,)).fetchall()
        
        # --- Prepare debug output data ---
        total_land_units = get_total_land_units(cursor, country)
        unit_limit_mod = get_country_modifier(cursor, country, "military_unit_limit_mult")
        unit_limit_mod *= get_building_country_modifier(cursor, country, "military_unit_limit_mult")
        land_unit_limit = int((population * BASE_UNIT_RATIO * unit_limit_mod) / POP_PER_UNIT + 5)
        navy_info = validate_navy_cap(cursor, country)
        
        print(
            f"\n=== {country} DEBUG INFO ==="
            f"\nPopulation: {population:,} → {new_total_population:,} (change: {political_mods['population_change']:+d})"
            f"\nLand Units: {total_land_units:,}/{land_unit_limit:,} (limit: {land_unit_limit:,})"
            f"\nNavy Units: {navy_info['current']:,}/{navy_info['cap']:,} (coastal: {navy_info['coastal_provinces']})"
            f"\nTax Income: {int(tax_income):,} (after corruption: {int(tax_income_after_corruption):,})"
            f"\nBuilding Income: {int(building_income):,}"
            f"\nTotal Income: {total_income:,}"
            f"\nAdministration Cost: {int(administration_cost):,}"
            f"\nLand Military Upkeep: {int(land_military_upkeep):,}"
            f"\nNavy Military Upkeep: {int(navy_military_upkeep):,}"
            f"\nBuilding Upkeep: {int(building_upkeep):,}"
            f"\nTotal Expenses: {total_expenses:,}"
            f"\nTreasury: {treasury:,} → {new_treasury:,}"
            f"\nResource Cap: {resource_cap:,} | Total Stockpile: {sum(s[1] for s in stockpile):,}"
            f"\nResource Production:"
        )
        if production:
            for resource_id, amount in sorted(production.items()):
                resource_name = resource_names.get(resource_id, f"ID_{resource_id}")
                print(f"   +{actually_added.get(resource_name, 0):,}/{amount:,} {resource_name}")
        print(f"\nPolitical State:")
        print(f"  Stability: {old_stability:.1f} → {new_stability:.1f} (change: {political_mods['stability_change']:.2f})")
        print(f"  Unrest: {old_unrest:.1f} → {new_unrest:.1f} (change: {political_mods['unrest_change']:.2f})")
        print(f"  Corruption: {old_corruption:.3f} → {new_corruption:.3f} (change: {political_mods['corruption_change']:.3f})")
        print(f"  War Exhaustion: {old_war_exhaustion:.1f} → {new_war_exhaustion:.1f} (change: {political_mods['war_exhaustion_change']:.2f})")
        print(f"  At War: {political_mods['at_war']}")
        print(f"  Tax Efficiency: {tax_eff:.3f} (political mod: {political_mods['tax_efficiency_mod']:.3f})")
        print(f"  Food: consumed {food_result['consumed']:,}/{food_result['required']:,} | shortage {food_result['shortage']:,} | tax x{food_tax_multiplier:.3f}")
        print(f"  Food Unrest Increase: {food_unrest_increase:.2f}")
        print(f"  Population Change: {political_mods['population_change']:+d}")
        print(f"  Economic Growth Rate: {total_growth_rate:.3f}")
        print(f"  Growth Amount: {growth_amount:,}")
        print("--------------------------------------------------")
    
    conn.commit()
    conn.close()
    print("\n✅ ECONOMY TICK COMPLETE\n")



if __name__ == "__main__":
    economy_tick()
