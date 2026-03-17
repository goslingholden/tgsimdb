from db_utils import get_connection
import configparser
from economy_tick import get_land_unit_cap, get_navy_unit_cap



config = configparser.ConfigParser()
config.read("config.ini")

MOVE_LOGGING = config.getboolean("moves", "logging", fallback=True)
BATCH_VALIDATE = config.getboolean("moves", "batch_validation", fallback=True)



def log(msg):
    if MOVE_LOGGING:
        print(msg)


def get_country_treasuries(cursor):
    cursor.execute("SELECT country_code, treasury FROM country_economy")
    return {c: t for c, t in cursor.fetchall()}

def ensure_country_resource_rows(cursor):
    cursor.execute("""
        INSERT OR IGNORE INTO country_resources (country_code, resource_id, stockpile)
        SELECT c.code, r.id, 0
        FROM countries c
        CROSS JOIN resources r
    """)


def get_country_resource_stockpiles(cursor):
    cursor.execute("SELECT country_code, resource_id, stockpile FROM country_resources")
    stockpiles = {}
    for country_code, resource_id, stockpile in cursor.fetchall():
        stockpiles.setdefault(country_code, {})[resource_id] = int(stockpile or 0)
    return stockpiles


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

def country_exists(cursor, country_code):
    cursor.execute("SELECT 1 FROM countries WHERE code = ?", (country_code,))
    return cursor.fetchone() is not None


def resource_exists(cursor, resource_id):
    cursor.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,))
    return cursor.fetchone() is not None


def get_resource_name(cursor, resource_id):
    cursor.execute("SELECT name FROM resources WHERE id = ?", (resource_id,))
    row = cursor.fetchone()
    return row[0] if row else f"resource_{resource_id}"


def get_building_resource_costs(cursor, building_type_id, amount):
    cursor.execute("""
        SELECT resource_id, amount_per_unit
        FROM building_resource_costs
        WHERE building_type_id = ?
    """, (building_type_id,))
    return {resource_id: per_unit * amount for resource_id, per_unit in cursor.fetchall()}


def get_unit_resource_costs(cursor, unit_type_id, amount):
    cursor.execute("""
        SELECT resource_id, amount_per_unit
        FROM unit_resource_costs
        WHERE unit_type_id = ?
    """, (unit_type_id,))
    return {resource_id: per_unit * amount for resource_id, per_unit in cursor.fetchall()}


def get_unit_category(cursor, unit_type_id):
    cursor.execute("SELECT unit_category FROM unit_types WHERE id = ?", (unit_type_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_current_unit_count(cursor, country_code, unit_category):
    cursor.execute("""
        SELECT COALESCE(SUM(cu.amount), 0)
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ? AND ut.unit_category = ?
    """, (country_code, unit_category))
    return cursor.fetchone()[0] or 0


def get_move_state(cursor):
    return {
        "treasuries": get_country_treasuries(cursor),
        "resource_stockpiles": get_country_resource_stockpiles(cursor),
        "unit_counts": {
            country_code: {
                "land": get_current_unit_count(cursor, country_code, "land"),
                "naval": get_current_unit_count(cursor, country_code, "naval"),
            }
            for country_code in get_country_treasuries(cursor)
        },
    }


def reserve_resource_costs(resource_stockpiles, country_code, resource_costs):
    country_stock = resource_stockpiles.setdefault(country_code, {})
    for resource_id, required in resource_costs.items():
        country_stock[resource_id] = country_stock.get(resource_id, 0) - required


def apply_resource_costs(cursor, country_code, resource_costs):
    for resource_id, required in resource_costs.items():
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile - ?
            WHERE country_code = ? AND resource_id = ?
        """, (required, country_code, resource_id))


def validate_trade_move(cursor, move, treasuries, resource_stockpiles):
    country = move["country_code"]
    partner = move["target_country_code"]
    amount = move["amount"]
    resource_id = move["target_resource_id"]
    move_type = move["move_type"]

    if not partner:
        return False, "Trade move missing target_country_code"
    if not country_exists(cursor, partner):
        return False, f"Trade target country does not exist: {partner}"
    if partner == country:
        return False, "Trade target country cannot be the same as source country"
    if not resource_id or not resource_exists(cursor, resource_id):
        return False, f"Invalid target_resource_id: {resource_id}"

    source_stock = resource_stockpiles.setdefault(country, {})
    partner_stock = resource_stockpiles.setdefault(partner, {})

    if move_type == "trade_resource_for_money":
        price_per_unit = int(move.get("price_per_unit") or 0)
        if price_per_unit <= 0:
            return False, "trade_resource_for_money requires price_per_unit > 0"

        if source_stock.get(resource_id, 0) < amount:
            return False, f"{country} lacks resources for trade (needs {amount})"

        total_price = price_per_unit * amount
        if treasuries.get(partner, 0) < total_price:
            return False, f"{partner} cannot afford trade (needs {total_price}, has {treasuries.get(partner, 0)})"

        source_stock[resource_id] = source_stock.get(resource_id, 0) - amount
        partner_stock[resource_id] = partner_stock.get(resource_id, 0) + amount
        treasuries[partner] -= total_price
        treasuries[country] += total_price

        move["__trade"] = {
            "kind": "money",
            "source_country": country,
            "target_country": partner,
            "resource_id": resource_id,
            "amount": amount,
            "price_per_unit": price_per_unit,
            "total_price": total_price
        }
        move["__cost"] = 0
        return True, "OK"

    if move_type == "trade_resource_for_resource":
        requested_resource_id = move["trade_resource_id"]
        if not requested_resource_id or not resource_exists(cursor, requested_resource_id):
            return False, f"Invalid trade_resource_id: {requested_resource_id}"
        if requested_resource_id == resource_id:
            return False, "trade_resource_for_resource requires two different resources"

        if source_stock.get(resource_id, 0) < amount:
            return False, f"{country} lacks offered resource (needs {amount})"
        if partner_stock.get(requested_resource_id, 0) < amount:
            return False, f"{partner} lacks requested resource (needs {amount})"

        source_stock[resource_id] = source_stock.get(resource_id, 0) - amount
        partner_stock[resource_id] = partner_stock.get(resource_id, 0) + amount
        partner_stock[requested_resource_id] = partner_stock.get(requested_resource_id, 0) - amount
        source_stock[requested_resource_id] = source_stock.get(requested_resource_id, 0) + amount

        move["__trade"] = {
            "kind": "resource",
            "source_country": country,
            "target_country": partner,
            "offered_resource_id": resource_id,
            "requested_resource_id": requested_resource_id,
            "amount": amount
        }
        move["__cost"] = 0
        return True, "OK"

    return False, f"Unknown trade move type: {move_type}"



def validate_political_move(cursor, move, treasuries):
    """Validate political action moves."""
    country = move["country_code"]
    amt = move["amount"]
    move_type = move["move_type"]
    
    
    politics = get_country_politics(cursor, country)
    if not politics:
        return False, f"{country} has no political data"
    
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    
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
        
    elif move_type == "make_peace":
        if not politics['at_war']:
            return False, f"{country} is not at war"
        
    else:
        return False, f"Unknown political move type: {move_type}"
    
    if treasuries[country] < cost:
        return False, f"{country} cannot afford {move_type} (needs {cost}, has {treasuries[country]})"
    
    
    treasuries[country] -= cost
    move["__cost"] = cost
    return True, "OK"


def validate_moves(cursor, moves, state=None):
    """
    Validates all moves and returns a list of approved ones with __cost set.
    Treasuries are tracked in a snapshot so sequential moves from the same
    country correctly account for each other's costs.
    """
    approved = []
    rejected = []
    state = state or get_move_state(cursor)
    treasuries = state["treasuries"]
    resource_stockpiles = state["resource_stockpiles"]
    unit_counts = state["unit_counts"]

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

        
        political_move_types = ["declare_war", "make_peace", "anti_corruption", 
                               "stabilize", "reduce_unrest", "propaganda_campaign", "war_effort"]
        trade_move_types = ["trade_resource_for_money", "trade_resource_for_resource"]
        
        if move["move_type"] in political_move_types:
            valid, msg = validate_political_move(cursor, move, treasuries)
            if not valid:
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue
            approved.append(move)
            continue

        if move["move_type"] in trade_move_types:
            valid, msg = validate_trade_move(cursor, move, treasuries, resource_stockpiles)
            if not valid:
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue
            approved.append(move)
            continue

        
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
            resource_costs = get_building_resource_costs(cursor, move["target_building_type_id"], amt)

        elif move["move_type"] == "recruit":
            if not unit_exists(cursor, move["target_unit_type_id"]):
                msg = f"Invalid unit id {move['target_unit_type_id']}"
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

            cursor.execute("SELECT recruitment_cost FROM unit_types WHERE id = ?", (move["target_unit_type_id"],))
            cost = cursor.fetchone()[0] * amt
            resource_costs = get_unit_resource_costs(cursor, move["target_unit_type_id"], amt)
            unit_category = get_unit_category(cursor, move["target_unit_type_id"])
            country_units = unit_counts.setdefault(country, {"land": 0, "naval": 0})
            current_units = country_units.get(unit_category, 0)

            if unit_category == "land":
                unit_cap = get_land_unit_cap(cursor, country)
            elif unit_category == "naval":
                unit_cap = get_navy_unit_cap(cursor, country)
            else:
                msg = f"Unknown unit category for unit {move['target_unit_type_id']}"
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

            if current_units + amt > unit_cap:
                msg = (
                    f"{country} would exceed {unit_category} unit cap "
                    f"({current_units + amt}/{unit_cap})"
                )
                log(f"❌ Move {move['id']}: {msg}")
                rejected.append((move["id"], msg))
                continue

        else:
            msg = f"Unknown move type '{move['move_type']}'"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        country_stock = resource_stockpiles.setdefault(country, {})
        missing_resources = []
        for resource_id, required in resource_costs.items():
            if country_stock.get(resource_id, 0) < required:
                missing_resources.append((resource_id, required, country_stock.get(resource_id, 0)))
        if missing_resources:
            details = ", ".join(
                f"{get_resource_name(cursor, rid)} needs {need}, has {have}"
                for rid, need, have in missing_resources
            )
            msg = f"{country} lacks resources for {move['move_type']}: {details}"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        if treasuries[country] < cost:
            msg = f"{country} cannot afford {move['move_type']} (needs {cost}, has {treasuries[country]})"
            log(f"❌ Move {move['id']}: {msg}")
            rejected.append((move["id"], msg))
            continue

        
        
        treasuries[country] -= cost
        reserve_resource_costs(resource_stockpiles, country, resource_costs)
        move["__cost"] = cost
        move["__resource_costs"] = resource_costs
        if move["move_type"] == "recruit":
            unit_counts[country][unit_category] += amt
        approved.append(move)

    return approved, rejected




def execute_political_move(cursor, move):
    """Execute a political action move."""
    country = move["country_code"]
    amt = move["amount"]
    move_type = move["move_type"]
    
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    
    cursor.execute("""
        SELECT stability, unrest, corruption, at_war, war_exhaustion
        FROM countries WHERE code = ?
    """, (country,))
    stability, unrest, corruption, at_war, war_exhaustion = cursor.fetchone()
    
    if move_type == "declare_war":
        cursor.execute("UPDATE countries SET at_war = 1 WHERE code = ?", (country,))
        msg = f"⚔ {country} declared war!"
    
    elif move_type == "make_peace":
        reduction = float(config["political_actions"]["peace_war_exhaustion_reduction"])
        new_war_exhaustion = max(0, war_exhaustion - reduction)
        cursor.execute("""
            UPDATE countries SET at_war = 0, war_exhaustion = ? WHERE code = ?
        """, (new_war_exhaustion, country))
        msg = f"☮ {country} made peace (war exhaustion reduced by {reduction})"
    
    elif move_type == "anti_corruption":
        reduction_per_unit = float(config["political_actions"]["anti_corruption_reduction_per_unit"])
        total_reduction = min(amt * reduction_per_unit, corruption)  
        new_corruption = max(0, corruption - total_reduction)
        cursor.execute("UPDATE countries SET corruption = ? WHERE code = ?", (new_corruption, country))
        msg = f"🔍 {country} reduced corruption by {total_reduction:.3f} (cost: {move['__cost']})"
    
    elif move_type == "stabilize":
        increase_per_unit = float(config["political_actions"]["stabilize_increase_per_unit"])
        total_increase = min(amt * increase_per_unit, 100 - stability)  
        new_stability = min(100, stability + total_increase)
        cursor.execute("UPDATE countries SET stability = ? WHERE code = ?", (new_stability, country))
        msg = f"📊 {country} increased stability by {total_increase} (cost: {move['__cost']})"
    
    elif move_type == "reduce_unrest":
        reduction_per_unit = float(config["political_actions"]["reduce_unrest_reduction_per_unit"])
        total_reduction = min(amt * reduction_per_unit, unrest)  
        new_unrest = max(0, unrest - total_reduction)
        cursor.execute("UPDATE countries SET unrest = ? WHERE code = ?", (new_unrest, country))
        msg = f"📉 {country} reduced unrest by {total_reduction} (cost: {move['__cost']})"
    
    elif move_type == "propaganda_campaign":
        stab_increase = amt * float(config["political_actions"]["propaganda_stability_increase"])
        unrest_reduction = amt * float(config["political_actions"]["propaganda_unrest_reduction"])
        new_stability = min(100, stability + stab_increase)
        new_unrest = max(0, unrest - unrest_reduction)
        cursor.execute("UPDATE countries SET stability = ?, unrest = ? WHERE code = ?", 
                      (new_stability, new_unrest, country))
        msg = f"📢 {country} propaganda: stability +{stab_increase}, unrest -{unrest_reduction} (cost: {move['__cost']})"
    
    elif move_type == "war_effort":
        reduction = amt * float(config["political_actions"]["war_effort_exhaustion_reduction"])
        new_war_exhaustion = max(0, war_exhaustion - reduction)
        cursor.execute("UPDATE countries SET war_exhaustion = ? WHERE code = ?", (new_war_exhaustion, country))
        msg = f"💪 {country} war effort reduced exhaustion by {reduction} (cost: {move['__cost']})"
    
    return msg


def execute_move(cursor, move):
    country = move["country_code"]
    cost = move["__cost"]

    if move["move_type"] == "trade_resource_for_money":
        trade = move["__trade"]
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile - ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["source_country"], trade["resource_id"]))
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile + ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["target_country"], trade["resource_id"]))
        cursor.execute("""
            UPDATE country_economy SET treasury = treasury + ?
            WHERE country_code = ?
        """, (trade["total_price"], trade["source_country"]))
        cursor.execute("""
            UPDATE country_economy SET treasury = treasury - ?
            WHERE country_code = ?
        """, (trade["total_price"], trade["target_country"]))
        resource_name = get_resource_name(cursor, trade["resource_id"])
        return (
            f"🤝 {trade['source_country']} sold {trade['amount']} {resource_name} to "
            f"{trade['target_country']} for {trade['total_price']}"
        )

    if move["move_type"] == "trade_resource_for_resource":
        trade = move["__trade"]
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile - ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["source_country"], trade["offered_resource_id"]))
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile + ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["target_country"], trade["offered_resource_id"]))
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile - ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["target_country"], trade["requested_resource_id"]))
        cursor.execute("""
            UPDATE country_resources
            SET stockpile = stockpile + ?
            WHERE country_code = ? AND resource_id = ?
        """, (trade["amount"], trade["source_country"], trade["requested_resource_id"]))
        offered_name = get_resource_name(cursor, trade["offered_resource_id"])
        requested_name = get_resource_name(cursor, trade["requested_resource_id"])
        return (
            f"🔄 {trade['source_country']} traded {trade['amount']} {offered_name} with "
            f"{trade['target_country']} for {trade['amount']} {requested_name}"
        )

    
    if cost > 0:
        cursor.execute("""
            UPDATE country_economy
            SET treasury = treasury - ?
            WHERE country_code = ?
        """, (cost, country))

    
    political_moves = ["declare_war", "make_peace", "anti_corruption", 
                      "stabilize", "reduce_unrest", "propaganda_campaign", "war_effort"]
    
    if move["move_type"] in political_moves:
        return execute_political_move(cursor, move)

    
    if move["move_type"] == "build":
        apply_resource_costs(cursor, country, move.get("__resource_costs", {}))
        cursor.execute("""
            INSERT INTO province_buildings (province_id, building_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(province_id, building_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (move["target_province_id"], move["target_building_type_id"], move["amount"]))

        return f"✅ {country} built {move['amount']}x building {move['target_building_type_id']} (cost {cost})"

    
    if move["move_type"] == "recruit":
        apply_resource_costs(cursor, country, move.get("__resource_costs", {}))
        cursor.execute("""
            INSERT INTO country_units (country_code, unit_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(country_code, unit_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (country, move["target_unit_type_id"], move["amount"]))

        return f"✅ {country} recruited {move['amount']}x unit {move['target_unit_type_id']} (cost {cost})"




def process_moves():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    ensure_country_resource_rows(cursor)
    conn.commit()

    cursor.execute("""
        SELECT id, turn, country_code, move_type,
               target_province_id, target_building_type_id,
               target_unit_type_id, target_country_code,
               target_resource_id, trade_resource_id, price_per_unit, amount
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
        "target_country_code": m[7],
        "target_resource_id": m[8],
        "trade_resource_id": m[9],
        "price_per_unit": m[10] or 0,
        "amount": m[11] or 1
    } for m in raw_moves]

    print(f"\n=== PROCESSING {len(moves)} MOVES ===\n")

    
    if BATCH_VALIDATE:
        approved_moves, rejected_moves = validate_moves(cursor, moves)
        log(f"\nApproved {len(approved_moves)} moves, rejected {len(rejected_moves)}")
    else:
        state = get_move_state(cursor)
        approved_moves = []
        rejected_moves = []
        for move in moves:
            approved, rejected = validate_moves(cursor, [move], state=state)
            approved_moves.extend(approved)
            rejected_moves.extend(rejected)
        log(f"\nApproved {len(approved_moves)} moves (individual validation mode)")

    try:
        conn.execute("BEGIN TRANSACTION;")

        
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




if __name__ == "__main__":
    process_moves()
