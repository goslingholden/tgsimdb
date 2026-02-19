from db_utils import get_connection
import csv
import os
import sys

MOVES_FOLDER = "moves"


# ================= UTILITIES =================

def clean(value):
    """Convert empty strings to None for SQLite NULL"""
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


# ================= IMPORT FUNCTION =================

def import_player_moves(turn_number):
    filename = os.path.join(MOVES_FOLDER, f"player_moves_turn_{turn_number}.csv")

    if not os.path.exists(filename):
        print(f"❌ No moves file found: {filename}")
        return

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Prevent double import
        cursor.execute("SELECT COUNT(*) FROM player_moves WHERE turn = ?", (turn_number,))
        if cursor.fetchone()[0] > 0:
            print(f"⚠ Turn {turn_number} already imported. Aborting.")
            conn.close()
            return

        # Open CSV
        with open(filename, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Validate CSV headers
            required_fields = {
                "country_code",
                "move_type",
                "province_id",
                "building_type_id",
                "unit_type_id",
                "amount",
                "notes"
            }

            missing = required_fields - set(reader.fieldnames)
            if missing:
                print(f"❌ Missing CSV columns: {missing}")
                conn.close()
                return

            move_count = 0

            # Begin transaction
            conn.execute("BEGIN TRANSACTION;")

            for row in reader:
                cursor.execute("""
                    INSERT INTO player_moves (
                        turn,
                        country_code,
                        move_type,
                        target_province_id,
                        target_building_type_id,
                        target_unit_type_id,
                        amount,
                        notes,
                        processed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    turn_number,
                    clean(row.get("country_code")),
                    clean(row.get("move_type")),
                    clean(row.get("province_id")),
                    clean(row.get("building_type_id")),
                    clean(row.get("unit_type_id")),
                    int(row.get("amount", 1) or 1),
                    clean(row.get("notes"))
                ))

                move_count += 1

            conn.commit()
            print(f"✅ Imported {move_count} moves for turn {turn_number}")

    except Exception as e:
        conn.rollback()
        print("❌ Import failed. Transaction rolled back.")
        print("ERROR:", e)

    finally:
        conn.close()


# ================= CLI ENTRYPOINT =================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py import_moves.py TURN_NUMBER")
        sys.exit(1)

    turn_number = sys.argv[1]
    import_player_moves(turn_number)