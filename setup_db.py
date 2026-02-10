from db_utils import get_connection

conn = get_connection()
cursor = conn.cursor()

# Enforce foreign keys
conn.execute("PRAGMA foreign_keys = ON;")

# -------------------- COUNTRIES --------------------
print("Building nations...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS countries (
    code TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    culture TEXT NOT NULL DEFAULT 'Unknown',
    religion TEXT NOT NULL DEFAULT 'Unknown',
    unrest INTEGER NOT NULL DEFAULT 0
);
""")
print("Nation-building completed.")

# -------------------- PROVINCES --------------------
print("Creating provinces table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS provinces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    population INTEGER NOT NULL,
    owner_country_code TEXT,
    rank TEXT NOT NULL DEFAULT 'settlement',
    religion TEXT NOT NULL DEFAULT 'Unknown',
    culture TEXT NOT NULL DEFAULT 'Unknown',
    terrain TEXT NOT NULL DEFAULT 'plains',
    FOREIGN KEY (owner_country_code) REFERENCES countries(code)
);
""")
print("Provinces table created successfully.")

# -------------------- STATES --------------------
print("Creating the states table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    food INTEGER NOT NULL DEFAULT 0,
    stability INTEGER NOT NULL DEFAULT 50,
    loyalty INTEGER NOT NULL DEFAULT 50
);
""")
print("States table created successfully.")

# -------------------- STATE-PROVINCE LINK --------------------
print("Creating state_provinces table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS state_provinces (
    state_id INTEGER,
    province_id INTEGER,
    PRIMARY KEY (state_id, province_id),
    FOREIGN KEY (state_id) REFERENCES states(id),
    FOREIGN KEY (province_id) REFERENCES provinces(id)
);
""")
print("State_provinces table created successfully.")

# ==========================================================
# ===================== ECONOMY SYSTEM ======================
# ==========================================================

# -------------------- BUILDING TYPES --------------------
print("Creating building_types table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS building_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    base_cost INTEGER NOT NULL,
    base_tax_income INTEGER NOT NULL DEFAULT 0,
    base_production INTEGER NOT NULL DEFAULT 0,
    description TEXT
);
""")
print("Building types table created successfully.")

# -------------------- PROVINCE BUILDINGS --------------------
print("Creating province_buildings table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS province_buildings (
    province_id INTEGER,
    building_type_id INTEGER,
    amount INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (province_id, building_type_id),
    FOREIGN KEY (province_id) REFERENCES provinces(id),
    FOREIGN KEY (building_type_id) REFERENCES building_types(id)
);
""")
print("Province buildings table created successfully.")

# -------------------- COUNTRY ECONOMY --------------------
print("Creating country_economy table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS country_economy (
    country_code TEXT PRIMARY KEY,
    treasury INTEGER NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.1,
    administration_cost INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (country_code) REFERENCES countries(code)
);
""")
print("Country economy table created successfully.")

print("✅ All tables have been created")

conn.commit()
conn.close()