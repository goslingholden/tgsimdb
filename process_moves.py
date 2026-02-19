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

def validate_moves(cursor, moves):
    """
    Returns list of approved moves
    """
    approved = []
    treasuries = get_country_treasuries(cursor)

    for move in moves:
        country = move["country_code"]
        amt = move["amount"]

        if amt <= 0:
            log(f"❌ Invalid amount in move {move['id']}")
            continue

        if move["move_type"] == "build":
            if not province_owned_by(cursor, move["target_province_id"], country):
                log(f"❌ {country} invalid province {move['target_province_id']}")
                continue

            if not building_exists(cursor, move["target_building_type_id"]):
                log(f"❌ Invalid building id {move['target_building_type_id']}")
                continue

            cursor.execute("SELECT base_cost FROM building_types WHERE id = ?", (move["target_building_type_id"],))
            cost = cursor.fetchone()[0] * amt

        elif move["move_type"] == "recruit":
            if not unit_exists(cursor, move["target_unit_type_id"]):
                log(f"❌ Invalid unit id {move['target_unit_type_id']}")
                continue

            cursor.execute("SELECT recruitment_cost FROM unit_types WHERE id = ?", (move["target_unit_type_id"],))
            cost = cursor.fetchone()[0] * amt

        else:
            log(f"❌ Unknown move type {move['move_type']}")
            continue

        if treasuries[country] < cost:
            log(f"❌ {country} cannot afford {move['move_type']} (needs {cost}, has {treasuries[country]})")
            continue

        # Reserve money in validation snapshot
        treasuries[country] -= cost
        move["__cost"] = cost
        approved.append(move)

    return approved


# ================= EXECUTION PHASE =================

def execute_move(cursor, move):
    country = move["country_code"]
    amt = move["amount"]
    cost = move["__cost"]

    # Deduct treasury
    cursor.execute("""
        UPDATE country_economy
        SET treasury = treasury - ?
        WHERE country_code = ?
    """, (cost, country))

    # BUILDINGS
    if move["move_type"] == "build":
        cursor.execute("""
            INSERT INTO province_buildings (province_id, building_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(province_id, building_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (move["target_province_id"], move["target_building_type_id"], amt))

        return f"✅ {country} built {amt}x building {move['target_building_type_id']} (cost {cost})"

    # UNITS
    if move["move_type"] == "recruit":
        cursor.execute("""
            INSERT INTO country_units (country_code, unit_type_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(country_code, unit_type_id)
            DO UPDATE SET amount = amount + excluded.amount
        """, (country, move["target_unit_type_id"], amt))

        return f"✅ {country} recruited {amt}x unit {move['target_unit_type_id']} (cost {cost})"


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
        approved_moves = validate_moves(cursor, moves)
        log(f"\nApproved {len(approved_moves)} moves, rejected {len(moves) - len(approved_moves)}")
    else:
        approved_moves = moves

    try:
        conn.execute("BEGIN TRANSACTION;")

        # ===== SIMULTANEOUS EXECUTION =====
        for move in approved_moves:
            msg = execute_move(cursor, move)
            log(msg)

            cursor.execute("UPDATE player_moves SET processed = 1 WHERE id = ?", (move["id"],))

        conn.commit()
        print(f"\n✅ EXECUTED {len(approved_moves)} MOVES SIMULTANEOUSLY\n")

    except Exception as e:
        conn.rollback()
        print("❌ MOVE PROCESSING FAILED. ROLLBACK EXECUTED.")
        print("ERROR:", e)

    finally:
        conn.close()


# ================= ENTRYPOINT =================

if __name__ == "__main__":
    process_moves()
