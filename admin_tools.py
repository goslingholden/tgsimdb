#!/usr/bin/env python3

import argparse
from db_utils import get_connection
from economy_tick import FOOD_RESOURCE_NAMES, ensure_country_resource_rows
from import_data import refresh_all_country_economies, refresh_country_economy, validate_schema


BASIC_FIELDS = {"capital", "government", "culture", "culture_group", "religion"}
POLITICAL_FIELDS = {"stability", "unrest", "corruption", "war_exhaustion", "at_war"}


def ensure_event_log_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            command_name TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_key TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            delta_value REAL,
            notes TEXT
        )
    """)


def fetch_row_dict(cursor, query, params=()):
    cursor.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def fetch_value(cursor, query, params=()):
    cursor.execute(query, params)
    row = cursor.fetchone()
    return row[0] if row else None


def to_numeric(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def stringify(value):
    if value is None:
        return None
    return str(value)


def log_change(cursor, command_name, target_table, target_key, field_name, old_value, new_value, notes=None):
    old_numeric = to_numeric(old_value)
    new_numeric = to_numeric(new_value)
    delta_value = None
    if old_numeric is not None and new_numeric is not None:
        delta_value = new_numeric - old_numeric

    cursor.execute("""
        INSERT INTO event_log (
            command_name, target_table, target_key, field_name,
            old_value, new_value, delta_value, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        command_name,
        target_table,
        target_key,
        field_name,
        stringify(old_value),
        stringify(new_value),
        delta_value,
        notes,
    ))


def log_summary(cursor, command_name, target_table, target_key, notes):
    cursor.execute("""
        INSERT INTO event_log (
            command_name, target_table, target_key, field_name,
            old_value, new_value, delta_value, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        command_name,
        target_table,
        target_key,
        "status",
        None,
        "executed",
        None,
        notes,
    ))


def require_country(cursor, country_code):
    if fetch_value(cursor, "SELECT 1 FROM countries WHERE code = ?", (country_code,)) != 1:
        raise ValueError(f"Country '{country_code}' does not exist")


def require_province(cursor, province_id):
    if fetch_value(cursor, "SELECT 1 FROM provinces WHERE id = ?", (province_id,)) != 1:
        raise ValueError(f"Province '{province_id}' does not exist")


def require_modifier(cursor, modifier_key):
    if fetch_value(cursor, "SELECT 1 FROM modifiers WHERE modifier_key = ?", (modifier_key,)) != 1:
        raise ValueError(f"Modifier '{modifier_key}' does not exist")


def resolve_building(cursor, building_ref):
    if str(building_ref).isdigit():
        row = fetch_row_dict(cursor, "SELECT id, name FROM building_types WHERE id = ?", (int(building_ref),))
    else:
        row = fetch_row_dict(cursor, "SELECT id, name FROM building_types WHERE name = ?", (building_ref,))
    if not row:
        raise ValueError(f"Building '{building_ref}' does not exist")
    return row


def resolve_unit(cursor, unit_ref):
    if str(unit_ref).isdigit():
        row = fetch_row_dict(cursor, "SELECT id, name FROM unit_types WHERE id = ?", (int(unit_ref),))
    else:
        row = fetch_row_dict(cursor, "SELECT id, name FROM unit_types WHERE name = ?", (unit_ref,))
    if not row:
        raise ValueError(f"Unit '{unit_ref}' does not exist")
    return row


def resolve_resource(cursor, resource_name):
    row = fetch_row_dict(cursor, "SELECT id, name FROM resources WHERE name = ?", (resource_name,))
    if not row:
        raise ValueError(f"Resource '{resource_name}' does not exist")
    return row


def parse_political_value(field, value):
    if field in {"stability", "unrest", "war_exhaustion"}:
        parsed = int(value)
        if not 0 <= parsed <= 100:
            raise ValueError(f"{field} must be between 0 and 100")
        return parsed
    if field == "corruption":
        parsed = float(value)
        if not 0.0 <= parsed <= 1.0:
            raise ValueError("corruption must be between 0.0 and 1.0")
        return parsed
    if field == "at_war":
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return 1
        if normalized in {"0", "false", "no", "n"}:
            return 0
        raise ValueError("at_war must be one of: 1, 0, true, false, yes, no")
    raise ValueError(f"Unsupported political field '{field}'")


def refresh_country_and_log(cursor, country_code, command_name, notes=None):
    before = fetch_row_dict(cursor, "SELECT * FROM country_economy WHERE country_code = ?", (country_code,))
    refresh_country_economy(cursor, country_code, seed_resource_stockpiles=False, verbose=False)
    after = fetch_row_dict(cursor, "SELECT * FROM country_economy WHERE country_code = ?", (country_code,))

    change_count = 0
    if before and after:
        for key, new_value in after.items():
            if key == "country_code":
                continue
            old_value = before.get(key)
            if old_value != new_value:
                log_change(
                    cursor,
                    command_name,
                    "country_economy",
                    country_code,
                    key,
                    old_value,
                    new_value,
                    notes or "Economy refreshed",
                )
                change_count += 1

    if change_count == 0:
        log_summary(cursor, command_name, "country_economy", country_code, notes or "Economy refresh produced no row changes")


def refresh_many_and_log(cursor, country_codes, command_name, notes=None):
    seen = set()
    for country_code in country_codes:
        if not country_code or country_code in seen:
            continue
        seen.add(country_code)
        refresh_country_and_log(cursor, country_code, command_name, notes=notes)


def set_basic(cursor, args):
    require_country(cursor, args.country_code)
    if args.field not in BASIC_FIELDS:
        raise ValueError(f"Field must be one of: {', '.join(sorted(BASIC_FIELDS))}")

    old_value = fetch_value(cursor, f"SELECT {args.field} FROM countries WHERE code = ?", (args.country_code,))
    new_value = args.value
    cursor.execute(f"UPDATE countries SET {args.field} = ? WHERE code = ?", (new_value, args.country_code))
    log_change(cursor, "set_basic", "countries", args.country_code, args.field, old_value, new_value)

    if args.field == "culture":
        current_group = fetch_value(cursor, "SELECT culture_group FROM countries WHERE code = ?", (args.country_code,))
        synced_group = fetch_value(cursor, "SELECT culture_group FROM cultures WHERE culture = ?", (new_value,))
        if synced_group and synced_group != current_group:
            cursor.execute("UPDATE countries SET culture_group = ? WHERE code = ?", (synced_group, args.country_code))
            log_change(
                cursor,
                "set_basic",
                "countries",
                args.country_code,
                "culture_group",
                current_group,
                synced_group,
                "Auto-synced from cultures table",
            )

    refresh_country_and_log(cursor, args.country_code, "set_basic", notes=f"Triggered by change to {args.field}")


def set_political(cursor, args):
    require_country(cursor, args.country_code)
    if args.field not in POLITICAL_FIELDS:
        raise ValueError(f"Field must be one of: {', '.join(sorted(POLITICAL_FIELDS))}")

    new_value = parse_political_value(args.field, args.value)
    old_value = fetch_value(cursor, f"SELECT {args.field} FROM countries WHERE code = ?", (args.country_code,))
    cursor.execute(f"UPDATE countries SET {args.field} = ? WHERE code = ?", (new_value, args.country_code))
    log_change(cursor, "set_political", "countries", args.country_code, args.field, old_value, new_value)
    refresh_country_and_log(cursor, args.country_code, "set_political", notes=f"Triggered by change to {args.field}")


def add_treasury(cursor, args, direction):
    require_country(cursor, args.country_code)
    if args.amount <= 0:
        raise ValueError("amount must be > 0")
    old_value = fetch_value(cursor, "SELECT treasury FROM country_economy WHERE country_code = ?", (args.country_code,))
    if old_value is None:
        raise ValueError(f"Country '{args.country_code}' has no economy row")

    amount = int(args.amount)
    delta = amount if direction == "add" else -amount
    new_value = old_value + delta
    if new_value < 0:
        raise ValueError(f"Treasury cannot go below 0 ({old_value} -> {new_value})")

    cursor.execute("UPDATE country_economy SET treasury = ? WHERE country_code = ?", (new_value, args.country_code))
    log_change(
        cursor,
        f"{direction}_treasury",
        "country_economy",
        args.country_code,
        "treasury",
        old_value,
        new_value,
    )


def set_tax_rate(cursor, args):
    require_country(cursor, args.country_code)
    new_value = float(args.tax_rate)
    if new_value < 0:
        raise ValueError("tax_rate must be >= 0")

    old_value = fetch_value(cursor, "SELECT tax_rate FROM country_economy WHERE country_code = ?", (args.country_code,))
    if old_value is None:
        raise ValueError(f"Country '{args.country_code}' has no economy row")

    cursor.execute("UPDATE country_economy SET tax_rate = ? WHERE country_code = ?", (new_value, args.country_code))
    log_change(cursor, "set_tax_rate", "country_economy", args.country_code, "tax_rate", old_value, new_value)
    refresh_country_and_log(cursor, args.country_code, "set_tax_rate", notes="Triggered by tax rate change")


def adjust_food(cursor, args, direction):
    require_country(cursor, args.country_code)
    ensure_country_resource_rows(cursor)
    if args.amount <= 0:
        raise ValueError("amount must be > 0")

    if args.resource_name not in FOOD_RESOURCE_NAMES:
        raise ValueError(
            f"'{args.resource_name}' is not a configured food resource. Allowed: {', '.join(FOOD_RESOURCE_NAMES)}"
        )

    resource = resolve_resource(cursor, args.resource_name)
    old_value = fetch_value(cursor, """
        SELECT stockpile
        FROM country_resources
        WHERE country_code = ? AND resource_id = ?
    """, (args.country_code, resource["id"]))
    old_value = int(old_value or 0)

    amount = int(args.amount)
    delta = amount if direction == "add" else -amount
    new_value = old_value + delta
    if new_value < 0:
        raise ValueError(f"Food stockpile cannot go below 0 ({old_value} -> {new_value})")

    cursor.execute("""
        UPDATE country_resources
        SET stockpile = ?
        WHERE country_code = ? AND resource_id = ?
    """, (new_value, args.country_code, resource["id"]))
    log_change(
        cursor,
        f"{direction}_food",
        "country_resources",
        f"{args.country_code}:{resource['name']}",
        "stockpile",
        old_value,
        new_value,
    )
    refresh_country_and_log(cursor, args.country_code, f"{direction}_food", notes="Triggered by food stockpile change")


def transfer_province(cursor, args):
    require_province(cursor, args.province_id)
    require_country(cursor, args.target_country_code)

    province = fetch_row_dict(
        cursor,
        "SELECT name, owner_country_code FROM provinces WHERE id = ?",
        (args.province_id,),
    )
    old_owner = province["owner_country_code"]
    new_owner = args.target_country_code
    cursor.execute("UPDATE provinces SET owner_country_code = ? WHERE id = ?", (new_owner, args.province_id))
    log_change(
        cursor,
        "transfer_province",
        "provinces",
        str(args.province_id),
        "owner_country_code",
        old_owner,
        new_owner,
        f"Province: {province['name']}",
    )
    refresh_many_and_log(
        cursor,
        [old_owner, new_owner],
        "transfer_province",
        notes=f"Triggered by province transfer of {province['name']}",
    )


def change_population(cursor, args):
    require_province(cursor, args.province_id)
    province = fetch_row_dict(
        cursor,
        "SELECT name, population, owner_country_code FROM provinces WHERE id = ?",
        (args.province_id,),
    )
    new_value = int(province["population"]) + int(args.delta)
    if new_value < 0:
        raise ValueError(f"Population cannot go below 0 ({province['population']} -> {new_value})")

    cursor.execute("UPDATE provinces SET population = ? WHERE id = ?", (new_value, args.province_id))
    log_change(
        cursor,
        "change_population",
        "provinces",
        str(args.province_id),
        "population",
        province["population"],
        new_value,
        f"Province: {province['name']}",
    )
    refresh_many_and_log(
        cursor,
        [province["owner_country_code"]],
        "change_population",
        notes=f"Triggered by population change in {province['name']}",
    )


def spawn_units(cursor, args):
    require_country(cursor, args.country_code)
    if args.amount <= 0:
        raise ValueError("amount must be > 0")
    unit = resolve_unit(cursor, args.unit_ref)
    old_value = fetch_value(cursor, """
        SELECT amount
        FROM country_units
        WHERE country_code = ? AND unit_type_id = ?
    """, (args.country_code, unit["id"]))
    old_value = int(old_value or 0)
    new_value = old_value + int(args.amount)

    cursor.execute("""
        INSERT INTO country_units (country_code, unit_type_id, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(country_code, unit_type_id)
        DO UPDATE SET amount = amount + excluded.amount
    """, (args.country_code, unit["id"], int(args.amount)))
    log_change(
        cursor,
        "spawn_units",
        "country_units",
        f"{args.country_code}:{unit['name']}",
        "amount",
        old_value,
        new_value,
    )
    refresh_country_and_log(cursor, args.country_code, "spawn_units", notes=f"Triggered by spawning {unit['name']}")


def add_building(cursor, args):
    require_province(cursor, args.province_id)
    if args.amount <= 0:
        raise ValueError("amount must be > 0")
    building = resolve_building(cursor, args.building_ref)
    province = fetch_row_dict(
        cursor,
        "SELECT name, owner_country_code FROM provinces WHERE id = ?",
        (args.province_id,),
    )
    old_value = fetch_value(cursor, """
        SELECT amount
        FROM province_buildings
        WHERE province_id = ? AND building_type_id = ?
    """, (args.province_id, building["id"]))
    old_value = int(old_value or 0)
    new_value = old_value + int(args.amount)

    cursor.execute("""
        INSERT INTO province_buildings (province_id, building_type_id, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(province_id, building_type_id)
        DO UPDATE SET amount = amount + excluded.amount
    """, (args.province_id, building["id"], int(args.amount)))
    log_change(
        cursor,
        "add_building",
        "province_buildings",
        f"{args.province_id}:{building['name']}",
        "amount",
        old_value,
        new_value,
        f"Province: {province['name']}",
    )
    refresh_many_and_log(
        cursor,
        [province["owner_country_code"]],
        "add_building",
        notes=f"Triggered by new {building['name']} in {province['name']}",
    )


def set_modifier(cursor, args):
    require_country(cursor, args.country_code)
    require_modifier(cursor, args.modifier_key)
    old_value = fetch_value(cursor, """
        SELECT value
        FROM country_modifiers
        WHERE country_code = ? AND modifier_key = ?
    """, (args.country_code, args.modifier_key))
    new_value = float(args.value)

    cursor.execute("""
        INSERT INTO country_modifiers (country_code, modifier_key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(country_code, modifier_key)
        DO UPDATE SET value = excluded.value
    """, (args.country_code, args.modifier_key, new_value))
    log_change(
        cursor,
        "set_modifier",
        "country_modifiers",
        f"{args.country_code}:{args.modifier_key}",
        "value",
        old_value,
        new_value,
    )
    refresh_country_and_log(cursor, args.country_code, "set_modifier", notes=f"Triggered by modifier {args.modifier_key}")


def add_modifier(cursor, args):
    require_country(cursor, args.country_code)
    require_modifier(cursor, args.modifier_key)
    old_value = fetch_value(cursor, """
        SELECT value
        FROM country_modifiers
        WHERE country_code = ? AND modifier_key = ?
    """, (args.country_code, args.modifier_key))
    old_value = float(old_value or 0.0)
    new_value = old_value + float(args.delta)

    cursor.execute("""
        INSERT INTO country_modifiers (country_code, modifier_key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(country_code, modifier_key)
        DO UPDATE SET value = value + excluded.value
    """, (args.country_code, args.modifier_key, float(args.delta)))
    log_change(
        cursor,
        "add_modifier",
        "country_modifiers",
        f"{args.country_code}:{args.modifier_key}",
        "value",
        old_value,
        new_value,
    )
    refresh_country_and_log(cursor, args.country_code, "add_modifier", notes=f"Triggered by modifier {args.modifier_key}")


def remove_modifier(cursor, args):
    require_country(cursor, args.country_code)
    require_modifier(cursor, args.modifier_key)
    old_value = fetch_value(cursor, """
        SELECT value
        FROM country_modifiers
        WHERE country_code = ? AND modifier_key = ?
    """, (args.country_code, args.modifier_key))
    if old_value is None:
        raise ValueError(f"{args.country_code} does not currently have modifier '{args.modifier_key}'")

    cursor.execute("""
        DELETE FROM country_modifiers
        WHERE country_code = ? AND modifier_key = ?
    """, (args.country_code, args.modifier_key))
    log_change(
        cursor,
        "remove_modifier",
        "country_modifiers",
        f"{args.country_code}:{args.modifier_key}",
        "value",
        old_value,
        0,
        "Modifier row deleted",
    )
    refresh_country_and_log(cursor, args.country_code, "remove_modifier", notes=f"Removed modifier {args.modifier_key}")


def refresh_country_command(cursor, args):
    require_country(cursor, args.country_code)
    refresh_country_and_log(cursor, args.country_code, "refresh_country", notes="Manual refresh")


def refresh_all_command(cursor, _args):
    before_rows = {
        row["country_code"]: row
        for row in (
            fetch_row_dict(cursor, "SELECT * FROM country_economy WHERE country_code = ?", (country_code,))
            for country_code in [code for code, in cursor.execute("SELECT code FROM countries ORDER BY code").fetchall()]
        )
        if row
    }
    refresh_all_country_economies(cursor, seed_resource_stockpiles=False, verbose=False)
    for country_code, before in before_rows.items():
        after = fetch_row_dict(cursor, "SELECT * FROM country_economy WHERE country_code = ?", (country_code,))
        if not after:
            continue
        changes = 0
        for key, new_value in after.items():
            if key == "country_code":
                continue
            old_value = before.get(key)
            if old_value != new_value:
                log_change(
                    cursor,
                    "refresh_all",
                    "country_economy",
                    country_code,
                    key,
                    old_value,
                    new_value,
                    "Manual refresh_all",
                )
                changes += 1
        if changes == 0:
            log_summary(cursor, "refresh_all", "country_economy", country_code, "Manual refresh_all produced no row changes")


def build_parser():
    parser = argparse.ArgumentParser(description="Admin helpers for safe mid-game database changes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_basic_parser = subparsers.add_parser("set-basic", help="Set a basic country field.")
    set_basic_parser.add_argument("country_code")
    set_basic_parser.add_argument("field")
    set_basic_parser.add_argument("value")

    set_political_parser = subparsers.add_parser("set-political", help="Set a political country field.")
    set_political_parser.add_argument("country_code")
    set_political_parser.add_argument("field")
    set_political_parser.add_argument("value")

    add_treasury_parser = subparsers.add_parser("add-treasury", help="Add treasury to a country.")
    add_treasury_parser.add_argument("country_code")
    add_treasury_parser.add_argument("amount", type=int)

    remove_treasury_parser = subparsers.add_parser("remove-treasury", help="Remove treasury from a country.")
    remove_treasury_parser.add_argument("country_code")
    remove_treasury_parser.add_argument("amount", type=int)

    tax_rate_parser = subparsers.add_parser("set-tax-rate", help="Set tax_rate for a country.")
    tax_rate_parser.add_argument("country_code")
    tax_rate_parser.add_argument("tax_rate", type=float)

    add_food_parser = subparsers.add_parser("add-food", help="Add a food resource stockpile to a country.")
    add_food_parser.add_argument("country_code")
    add_food_parser.add_argument("resource_name")
    add_food_parser.add_argument("amount", type=int)

    remove_food_parser = subparsers.add_parser("remove-food", help="Remove a food resource stockpile from a country.")
    remove_food_parser.add_argument("country_code")
    remove_food_parser.add_argument("resource_name")
    remove_food_parser.add_argument("amount", type=int)

    transfer_parser = subparsers.add_parser("transfer-province", help="Transfer a province to another country.")
    transfer_parser.add_argument("province_id", type=int)
    transfer_parser.add_argument("target_country_code")

    population_parser = subparsers.add_parser("change-population", help="Add or remove province population by delta.")
    population_parser.add_argument("province_id", type=int)
    population_parser.add_argument("delta", type=int)

    spawn_parser = subparsers.add_parser("spawn-units", help="Spawn units for a country.")
    spawn_parser.add_argument("country_code")
    spawn_parser.add_argument("unit_ref")
    spawn_parser.add_argument("amount", type=int)

    building_parser = subparsers.add_parser("add-building", help="Add buildings to a province.")
    building_parser.add_argument("province_id", type=int)
    building_parser.add_argument("building_ref")
    building_parser.add_argument("amount", type=int)

    set_modifier_parser = subparsers.add_parser("set-modifier", help="Set a country modifier to an exact value.")
    set_modifier_parser.add_argument("country_code")
    set_modifier_parser.add_argument("modifier_key")
    set_modifier_parser.add_argument("value", type=float)

    add_modifier_parser = subparsers.add_parser("add-modifier", help="Add a delta to a country modifier.")
    add_modifier_parser.add_argument("country_code")
    add_modifier_parser.add_argument("modifier_key")
    add_modifier_parser.add_argument("delta", type=float)

    remove_modifier_parser = subparsers.add_parser("remove-modifier", help="Remove a country modifier row.")
    remove_modifier_parser.add_argument("country_code")
    remove_modifier_parser.add_argument("modifier_key")

    refresh_country_parser = subparsers.add_parser("refresh-country", help="Refresh derived economy data for one country.")
    refresh_country_parser.add_argument("country_code")

    subparsers.add_parser("refresh-all", help="Refresh derived economy data for all countries.")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        ensure_event_log_table(cursor)
        validate_schema(cursor)
        ensure_country_resource_rows(cursor)

        if args.command == "set-basic":
            set_basic(cursor, args)
        elif args.command == "set-political":
            set_political(cursor, args)
        elif args.command == "add-treasury":
            add_treasury(cursor, args, "add")
        elif args.command == "remove-treasury":
            add_treasury(cursor, args, "remove")
        elif args.command == "set-tax-rate":
            set_tax_rate(cursor, args)
        elif args.command == "add-food":
            adjust_food(cursor, args, "add")
        elif args.command == "remove-food":
            adjust_food(cursor, args, "remove")
        elif args.command == "transfer-province":
            transfer_province(cursor, args)
        elif args.command == "change-population":
            change_population(cursor, args)
        elif args.command == "spawn-units":
            spawn_units(cursor, args)
        elif args.command == "add-building":
            add_building(cursor, args)
        elif args.command == "set-modifier":
            set_modifier(cursor, args)
        elif args.command == "add-modifier":
            add_modifier(cursor, args)
        elif args.command == "remove-modifier":
            remove_modifier(cursor, args)
        elif args.command == "refresh-country":
            refresh_country_command(cursor, args)
        elif args.command == "refresh-all":
            refresh_all_command(cursor, args)
        else:
            raise ValueError(f"Unsupported command '{args.command}'")

        conn.commit()
        print(f"Command '{args.command}' completed successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"Command '{args.command}' failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
