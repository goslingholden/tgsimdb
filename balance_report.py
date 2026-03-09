import argparse
import contextlib
import io
import subprocess
import sys

from db_utils import get_connection
from economy_tick import economy_tick


def run_command(cmd):
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def wipe_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF;")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]

    for table_name in table_names:
        cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')

    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()


def reset_world():
    print("Resetting world state from CSV data...")
    wipe_database()
    run_command(["python3", "setup_db.py"])
    run_command(["python3", "import_data.py"])


def load_snapshot():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.code,
            ce.treasury,
            ce.total_population,
            c.unrest,
            c.stability
        FROM countries c
        JOIN country_economy ce ON ce.country_code = c.code
        ORDER BY c.code
        """
    )
    rows = cursor.fetchall()
    conn.close()

    return {
        code: {
            "treasury": treasury or 0,
            "population": population or 0,
            "unrest": float(unrest or 0.0),
            "stability": float(stability or 0.0),
        }
        for code, treasury, population, unrest, stability in rows
    }


def ensure_country(stats, code):
    if code not in stats:
        stats[code] = {
            "ticks": 0,
            "treasury_delta_sum": 0.0,
            "treasury_pct_sum": 0.0,
            "population_delta_sum": 0.0,
            "population_pct_sum": 0.0,
            "unrest_delta_sum": 0.0,
            "stability_delta_sum": 0.0,
            "max_treasury_pct": float("-inf"),
            "min_treasury_pct": float("inf"),
        }
    return stats[code]


def apply_tick_deltas(stats, before, after):
    for code, b in before.items():
        if code not in after:
            continue
        a = after[code]
        entry = ensure_country(stats, code)
        entry["ticks"] += 1

        treasury_delta = a["treasury"] - b["treasury"]
        population_delta = a["population"] - b["population"]
        unrest_delta = a["unrest"] - b["unrest"]
        stability_delta = a["stability"] - b["stability"]

        treasury_pct = (treasury_delta / b["treasury"] * 100.0) if b["treasury"] > 0 else 0.0
        population_pct = (population_delta / b["population"] * 100.0) if b["population"] > 0 else 0.0

        entry["treasury_delta_sum"] += treasury_delta
        entry["treasury_pct_sum"] += treasury_pct
        entry["population_delta_sum"] += population_delta
        entry["population_pct_sum"] += population_pct
        entry["unrest_delta_sum"] += unrest_delta
        entry["stability_delta_sum"] += stability_delta
        entry["max_treasury_pct"] = max(entry["max_treasury_pct"], treasury_pct)
        entry["min_treasury_pct"] = min(entry["min_treasury_pct"], treasury_pct)


def format_row(code, entry):
    ticks = max(1, entry["ticks"])
    avg_treasury_delta = entry["treasury_delta_sum"] / ticks
    avg_treasury_pct = entry["treasury_pct_sum"] / ticks
    avg_population_delta = entry["population_delta_sum"] / ticks
    avg_population_pct = entry["population_pct_sum"] / ticks
    avg_unrest_delta = entry["unrest_delta_sum"] / ticks
    avg_stability_delta = entry["stability_delta_sum"] / ticks

    return (
        f"{code:>3} | "
        f"treasury {avg_treasury_delta:>8.1f} ({avg_treasury_pct:>6.2f}%) | "
        f"pop {avg_population_delta:>8.1f} ({avg_population_pct:>5.2f}%) | "
        f"unrest {avg_unrest_delta:>6.2f} | "
        f"stab {avg_stability_delta:>6.2f} | "
        f"treasury% range [{entry['min_treasury_pct']:>6.2f}, {entry['max_treasury_pct']:>6.2f}]"
    )


def print_summary(stats, ticks):
    print("\n=== BALANCE REPORT ===")
    print(f"Ticks simulated: {ticks}")
    print("Per country average deltas per tick:")
    print(
        "CCC | treasury(avg) | pop(avg) | unrest(avg) | stab(avg) | treasury% range"
    )

    rows = sorted(stats.items(), key=lambda item: item[1]["treasury_pct_sum"] / max(1, item[1]["ticks"]), reverse=True)
    for code, entry in rows:
        print(format_row(code, entry))

    if not rows:
        print("No country data.")
        return

    avg_global_treasury_pct = sum(
        entry["treasury_pct_sum"] / max(1, entry["ticks"]) for _, entry in rows
    ) / len(rows)
    avg_global_unrest_delta = sum(
        entry["unrest_delta_sum"] / max(1, entry["ticks"]) for _, entry in rows
    ) / len(rows)

    print("\nGlobal indicators:")
    print(f"- Average treasury growth per tick: {avg_global_treasury_pct:.2f}%")
    print(f"- Average unrest change per tick: {avg_global_unrest_delta:.2f}")

    high_growth = [code for code, e in rows if (e["treasury_pct_sum"] / max(1, e["ticks"])) > 5.0]
    unrest_spike = [code for code, e in rows if (e["unrest_delta_sum"] / max(1, e["ticks"])) > 1.5]

    print("\nPotential balance flags:")
    print(f"- Countries with avg treasury growth > 5%/tick: {', '.join(high_growth) if high_growth else 'none'}")
    print(f"- Countries with avg unrest increase > 1.5/tick: {', '.join(unrest_spike) if unrest_spike else 'none'}")


def run_report(ticks, fresh, verbose_ticks):
    if fresh:
        reset_world()

    before = load_snapshot()
    if not before:
        raise RuntimeError("No countries found in database.")

    stats = {}
    for tick_index in range(1, ticks + 1):
        print(f"Running tick {tick_index}/{ticks}...")
        if verbose_ticks:
            economy_tick()
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                economy_tick()
        after = load_snapshot()
        apply_tick_deltas(stats, before, after)
        before = after

    print_summary(stats, ticks)


def parse_args():
    parser = argparse.ArgumentParser(description="Run multiple economy ticks and print balance trends.")
    parser.add_argument("--ticks", type=int, default=10, help="Number of economy ticks to simulate (default: 10)")
    parser.add_argument(
        "--fresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reset DB from CSV files before running (default: --fresh)",
    )
    parser.add_argument(
        "--verbose-ticks",
        action="store_true",
        help="Show full economy_tick output for each tick",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.ticks <= 0:
        print("Ticks must be greater than zero.")
        sys.exit(1)

    try:
        run_report(args.ticks, args.fresh, args.verbose_ticks)
    except Exception as exc:
        print(f"❌ Balance report failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
