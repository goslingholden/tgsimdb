from db_utils import get_connection
import configparser

# ================= LOAD CONFIG =================

config = configparser.ConfigParser()
config.read("config.ini")

MOVE_LOGGING = config.getboolean("moves", "logging", fallback=True)
SIMULTANEOUS = config.getboolean("moves", "simultaneous_resolution", fallback=True)
BATCH_VALIDATE = config.getboolean("moves", "batch_validation", fallback=True)

# ================= UTILITIES =================

def log(msg):
    if MOVE_LOGGING:
        print(msg)


def get_country_treasuries(cursor):
    cursor.execute("SELECT country_code, treasury FROM country_economy")
    return {c: t for c, t in cursor.fetchall()}


def get_country_politics(cursor, country_code):
    """Get current political values for a country."""
    cursor.execute("""
        SELECT stability, unrest, corruption, at_war, war_exhaustion
        FROM countries WHERE code = ?
    """, (country_code,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'stability': row[0],
        'unrest': row[1],
        'corruption': row[2],
        'at_war': row[3],
        'war_exhaustion': row[4]
    }


def province_owned_by(cursor, province_id, country):
    cursor.execute("""
        SELECT 1 FROM provinces
        WHERE id = ? AND owner_country_code = ?
    """, (province_id, country))
    return cursor.fetchone() is not None


def building_exists(cursor, building_type_id):
    cursor.execute("SELECT 1 FROM building_types WHERE id = ?", (building_type_id,))
    return cursor.fetchone() is not None


def unit_exists(cursor, unit_type_id):
    cursor.execute("SELECT 1 FROM unit_types WHERE id = ?", (unit_type_id,))
    return cursor.fetchone() is not None


# ================= VALIDATION PHASE =================

def validate_political_move(cursor, move, treasuries):
    """Validate political action moves."""
    country = move["country_code"]
    amt = move["amount"]
    move_type = move["move_type"]
    
    # Get current political state
    politics = get_country_politics(cursor, country)
    if not politics:
        return False, f"{country} has no political data"
    
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    # Check affordability
    cost = 0
    if move_type == "anti_corruption":
        cost = amt * float(config["political_actions"]["anti_corruption_cost_per_unit"])
        if politics['corruption'] <= 0:
            return False, f"{country} has no corruption to reduce"
    elif move_type == "stabilize":
        cost = amt * float(config["political_actions"]["stabilize_cost_per_unit"])
        if politics['stability'] >= 100:
            return False, f"{country} stability already at maximum"
    elif move_type == "reduce_unrest":
        cost = amt * float(config["political_actions"]["reduce_unrest_cost_per_unit"])
        if politics['unrest'] <= 0:
            return False, f"{country} has no unrest to reduce"
    elif move_type == "propaganda_campaign":
        cost = amt * float(config["political_actions"]["propaganda_cost_per_unit"])
    elif move_type == "war_effort":
        cost = amt * float(config["political_actions"]["war_effort_cost_per_unit"])
        if not politics['at_war']:
            return False, f"{country} is not at war"
        if politics['war_exhaustion'] <= 0:
            return False, f"{country} has no war exhaustion"
    elif move_type == "declare_war":
        if politics['at_war']:
            return False, f"{country} is already at war"
        # No cost for declaring war
    elif move_type == "make_peace":
        if not politics['at_war']:
            return False, f"{country} is not at war"
        # No cost for making peace
    else:
        return False, f"Unknown political move type: {move_type}"
    
    if treasuries[country] < cost:
        return False, f"{country} cannot afford {move_type} (needs {cost}, has {treasuries[country]})"
    
    # Reserve cost
    treasuries[country] -= cost
    move["__cost"] = cost
    return True, "OK"


def validate_moves(cursor, moves):
    """
    Validates all moves and returns a list of approved ones with __cost set.
    Treasuries are tracked in a snapshot so sequential moves from the same
    country correctly account for each other's costs.
    """
    approved = []
    rejected = []
    treasuries = get_country_treasuries(cursor)

    for move in moves:
        country = move["country_code"]
        amt = move["amount"]

        if country not in treasuries:
            msg = f"{country} has no economy record, skipping."
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        if amt <= 0:
            msg = f"Invalid amount ({amt})"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        # ===== POLITICAL MOVES =====
        political_move_types = ["declare_war", "make_peace", "anti_corruption", 
                               "stabilize", "reduce_unrest", "propaganda_campaign", "war_effort"]
        
        if move["move_type"] in political_move_types:
            valid, msg = validate_political_move(cursor, move, treasuries)
            if not valid:
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue
            approved.append(move)
            continue

        # ===== EXISTING VALIDATION (build, recruit) =====
        if move["move_type"] == "build":
            if not province_owned_by(cursor, move["target_province_id"], country):
                msg = f"{country} does not own province {move['target_province_id']}"
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

            if not building_exists(cursor, move["target_building_type_id"]):
                msg = f"Invalid building id {move['target_building_type_id']}"
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

            cursor.execute("SELECT base_cost FROM building_types WHERE id = ?", (move["target_building_type_id"],))
            cost = cursor.fetchone()[0] * amt

        elif move["move_type"] == "recruit":
            if not unit_exists(cursor, move["target_unit_type_id"]):
                msg = f"Invalid unit id {move['target_unit_type_id']}"
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

            cursor.execute("SELECT recruitment_cost FROM unit_types WHERE id = ?", (move["target_unit_type_id"],))
            cost = cursor.fetchone()[0] * amt

        else:
            msg = f"Unknown move type '{move['move_type']}'"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        if treasuries[country] < cost:
            msg = f"{country} cannot afford {move['move_type']} (needs {cost}, has {treasuries[country]})"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        # Reserve cost in the snapshot so later moves from the same country
        # correctly see the reduced treasury
        treasuries[country] -= cost
        move["__cost"] = cost
        approved.append(move)

    return approved, rejected


# ================= EXECUTION PHASE =================

def execute_political_move(cursor, move):
    """Execute a political action move."""
    country = move["country_code"]
    amt = move["amount"]
    move_type = move["move_type"]
    
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    # Get current values
    cursor.execute("""
        SELECT stability, unrest, corruption, at_war, war_exhaustion
        FROM countries WHERE code = ?
    """, (country,))
    stability, unrest, corruption, at_war, war_exhaustion = cursor.fetchone()
    
    changes = {}
    
    if move_type == "declare_war":
        cursor.execute("UPDATE countries SET at_war = 1 WHERE code = ?", (country,))
        changes = {'at_war': 1, 'war_exhaustion': war_exhaustion}
        msg = f"⚔ {country} declared war!"
    
    elif move_type == "make_peace":
        reduction = float(config["political_actions"]["peace_war_exhaustion_reduction"])
        new_war_exhaustion = max(0, war_exhaustion - reduction)
        cursor.execute("""
            UPDATE countries SET at_war = 0, war_exhaustion = ? WHERE code = ?
        """, (new_war_exhaustion, country))
        changes = {'at_war': 1, 'war_exhaustion': new_war_exhaustion}
        msg = f"☮ {country} made peace (war exhaustion reduced by {reduction})"
    
    elif move_type == "anti_corruption":
        reduction_per_unit = float(config["political_actions"]["anti_corruption_reduction_per_unit"])
        total_reduction = min(amt * reduction_per_unit, corruption)  # Can't go below 0
        new_corruption = max(0, corruption - total_reduction)
        cursor.execute("UPDATE countries SET corruption = ? WHERE code = ?", (new_corruption, country))
        changes = {'corruption': new_corruption}
        msg = f"🔍 {country} reduced corruption by {total_reduction:.3f} (cost: {move['__cost']})"
    
    elif move_type == "stabilize":
        increase_per_unit = float(config["political_actions"]["stabilize_increase_per_unit"])
        total_increase = min(amt * increase_per_unit, 100 - stability)  # Cap at 100
        new_stability = min(100, stability + total_increase)
        cursor.execute("UPDATE countries SET stability = ? WHERE code = ?", (new_stability, country))
        changes = {'stability': new_stability}
        msg = f"📊 {country} increased stability by {total_increase} (cost: {move['__cost']})"
    
    elif move_type == "reduce_unrest":
        reduction_per_unit = float(config["political_actions"]["reduce_unrest_reduction_per_unit"])
        total_reduction = min(amt * reduction_per_unit, unrest)  # Can't go below 0
        new_unrest = max(0, unrest - total_reduction)
        cursor.execute("UPDATE countries SET unrest = ? WHERE code = ?", (new_unrest, country))
        changes = {'unrest': new_unrest}
        msg = f"📉 {country} reduced unrest by {total_reduction} (cost: {move['__cost']})"
    
    elif move_type == "propaganda_campaign":
        stab_increase = amt * float(config["political_actions"]["propaganda_stability_increase"])
        unrest_reduction = amt * float(config["political_actions"]["propaganda_unrest_reduction"])
        new_stability = min(100, stability + stab_increase)
        new_unrest = max(0, unrest - unrest_reduction)
        cursor.execute("UPDATE countries SET stability = ?, unrest = ? WHERE code = ?", 
                      (new_stability, new_unrest, country))
        changes = {'stability': new_stability, 'unrest': new_unrest}
        msg = f"📢 {country} propaganda: stability +{stab_increase}, unrest -{unrest_reduction} (cost: {move['__cost']})"
    
    elif move_type == "war_effort":
        reduction = amt * float(config["political_actions"]["war_effort_exhaustion_reduction"])
        new_war_exhaustion = max(0, war_exhaustion - reduction)
        cursor.execute("UPDATE countries SET war_exhaustion = ? WHERE code = ?", (new_war_exhaustion, country))
        changes = {'war_exhaustion': new_war_exhaustion}
        msg = f"💪 {country} war effort reduced exhaustion by {reduction} (cost: {move['__cost']})"
    
    return msg, changes


def execute_move(cursor, move):
    country = move["country_code"]
    cost = move["__cost"]

    # Deduct treasury (for all moves that have a cost)
    if cost > 0:
        cursor.execute("""
            UPDATE country_economy
            SET treasury = treasury - ?
            WHERE country_code = ?
        """, (cost, country))

    # POLITICAL MOVES
    political_moves = ["declare_war", "make_peace", "anti_corruption", 
                      "stabilize", "reduce_unrest", "propaganda_campaign", "war_effort"]
    
    if move["move_type"] in political_moves:
        msg, changes = execute_political_move(cursor, move)
        return msg

    # BUILDINGS
    if move["move_type"] == "build":
        cursor.execute("""
            INSERT INTO province_buildings (province_id, building_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(province_id, building_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (move["target_province_id"], move["target_building_type_id"], move["amount"]))

        return f"✅ {country} built {move['amount']}x building {move['target_building_type_id']} (cost {cost})"

    # UNITS
    if move["move_type"] == "recruit":
        cursor.execute("""
            INSERT INTO country_units (country_code, unit_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(country_code, unit_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (country, move["target_unit_type_id"], move["amount"]))

        return f"✅ {country} recruited {move['amount']}x unit {move['target_unit_type_id']} (cost {cost})"


# ================= MAIN PROCESSOR =================

def process_moves():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, turn, country_code, move_type,
               target_province_id, target_building_type_id,
               target_unit_type_id, amount
        FROM player_moves
        WHERE processed = 0
        ORDER BY turn, id
    """)

    raw_moves = cursor.fetchall()
    if not raw_moves:
        print("No moves to process.")
        conn.close()
        return

    moves = [{
        "id": m[0],
        "turn": m[1],
        "country_code": m[2],
        "move_type": m[3],
        "target_province_id": m[4],
        "target_building_type_id": m[5],
        "target_unit_type_id": m[6],
        "amount": m[7] or 1
    } for m in raw_moves]

    print(f"\n=== PROCESSING {len(moves)} MOVES ===\n")

    # ===== VALIDATION PASS =====
    if BATCH_VALIDATE:
        approved_moves, rejected_moves = validate_moves(cursor, moves)
        log(f"\nApproved {len(approved_moves)} moves, rejected {len(rejected_moves)}")
    else:
        # Validate each move independently without shared treasury tracking
        approved_moves = []
        rejected_moves = []
        for move in moves:
            approved, rejected = validate_moves(cursor, [move])
            approved_moves.extend(approved)
            rejected_moves.extend(rejected)
        log(f"\nApproved {len(approved_moves)} moves (individual validation mode)")

    try:
        conn.execute("BEGIN TRANSACTION;")

        # ===== EXECUTION =====
        for move in approved_moves:
            msg = execute_move(cursor, move)
            log(msg)
            cursor.execute("UPDATE player_moves SET processed = 1 WHERE id = ?", (move["id"],))

        for move_id, error_msg in rejected_moves:
            cursor.execute("""
                UPDATE player_moves
                SET processed = 1, error_message = ?
                WHERE id = ?
            """, (error_msg, move_id))

        conn.commit()
        print(f"\n✅ EXECUTED {len(approved_moves)} MOVES | REJECTED {len(rejected_moves)} MOVES\n")

    except Exception as e:
        conn.rollback()
        print("❌ MOVE PROCESSING FAILED. ROLLBACK EXECUTED.")
        print("ERROR:", e)

    finally:
        conn.close()


# ================= ENTRYPOINT =================

if __name__ == "__main__":
    process_moves()
