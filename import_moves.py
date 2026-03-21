from db_utils import get_connection
import csv
import os
import sys

MOVES_FOLDER = "moves"




def clean(value):
    """Convert empty strings to None for SQLite NULL"""
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def resolve_moves_dir(folder_name=None):
    if folder_name:
        moves_dir = os.path.join(MOVES_FOLDER, folder_name)
    else:
        moves_dir = MOVES_FOLDER

    if not os.path.isdir(moves_dir):
        raise FileNotFoundError(f"Moves directory not found: {moves_dir}")
    return moves_dir


def get_moves_file(moves_dir, turn_number):
    filename = os.path.join(moves_dir, f"player_moves_turn_{turn_number}.csv")
    if not os.path.exists(filename):
        raise FileNotFoundError(f"No moves file found: {filename}")
    return filename


def parse_args(argv):
    if len(argv) < 2:
        print("Usage: py import_moves.py TURN_NUMBER [MOVES_SUBFOLDER]")
        print('Example: py import_moves.py 1 "Diadochi 322 AC Partita 1"')
        sys.exit(1)

    try:
        turn_number = int(argv[1])
    except ValueError:
        print(f"❌ Invalid turn number: '{argv[1]}' — must be an integer.")
        sys.exit(1)

    moves_subfolder = argv[2] if len(argv) > 2 else None
    return turn_number, moves_subfolder




def import_player_moves(turn_number, moves_subfolder=None):
    turn_number = int(turn_number)
    moves_dir = resolve_moves_dir(moves_subfolder)
    filename = get_moves_file(moves_dir, turn_number)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        
        cursor.execute("SELECT COUNT(*) FROM player_moves WHERE turn = ?", (turn_number,))
        if cursor.fetchone()[0] > 0:
            print(f"⚠ Turn {turn_number} already imported. Aborting.")
            conn.close()
            return

        
        with open(filename, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            
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

            for row in reader:
                cursor.execute("""
                    INSERT INTO player_moves (
                        turn,
                        country_code,
                        move_type,
                        target_province_id,
                        target_building_type_id,
                        target_unit_type_id,
                        target_country_code,
                        target_resource_id,
                        trade_resource_id,
                        price_per_unit,
                        amount,
                        notes,
                        processed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    turn_number,
                    clean(row.get("country_code")),
                    clean(row.get("move_type")),
                    clean(row.get("province_id")),
                    clean(row.get("building_type_id")),
                    clean(row.get("unit_type_id")),
                    clean(row.get("target_country_code")),
                    clean(row.get("target_resource_id")),
                    clean(row.get("trade_resource_id")),
                    int(row.get("price_per_unit", 0) or 0),
                    int(row.get("amount", 1) or 1),
                    clean(row.get("notes"))
                ))

                move_count += 1

        conn.commit()
        print(f"✅ Imported {move_count} moves for turn {turn_number} from {filename}")

    except Exception as e:
        conn.rollback()
        print("❌ Import failed. Transaction rolled back.")
        print("ERROR:", e)

    finally:
        conn.close()




if __name__ == "__main__":
    turn_number, moves_subfolder = parse_args(sys.argv)
    import_player_moves(turn_number, moves_subfolder)
