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
# ===================== ECONOMY SYSTEM =====================
# ==========================================================

# -------------------- BUILDING TYPES --------------------
print("Creating building_types table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS building_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    building_type TEXT UNIQUE NOT NULL,
    base_cost INTEGER NOT NULL,
    base_tax_income INTEGER NOT NULL DEFAULT 0,
    base_production INTEGER NOT NULL DEFAULT 0,
    base_upkeep INTEGER NOT NULL DEFAULT 0,
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

    -- Income
    tax_income INTEGER NOT NULL DEFAULT 0,
    building_income INTEGER NOT NULL DEFAULT 0,
    total_income INTEGER NOT NULL DEFAULT 0,

    -- Expenses
    administration_cost INTEGER NOT NULL DEFAULT 0,
    building_upkeep INTEGER NOT NULL DEFAULT 0,
    military_upkeep INTEGER NOT NULL DEFAULT 0,
    total_expenses INTEGER NOT NULL DEFAULT 0,

    -- Modifiers
    tax_efficiency REAL NOT NULL DEFAULT 1.0,
    corruption REAL NOT NULL DEFAULT 0.0,
    economic_growth REAL NOT NULL DEFAULT 0.0,

    -- Snapshot data
    total_population INTEGER NOT NULL DEFAULT 0,

    -- Crisis flags
    at_war INTEGER NOT NULL DEFAULT 0,
    war_exhaustion INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (country_code) REFERENCES countries(code)
);
""")
print("Country economy table created successfully.")

# ==========================================================
# ==================== MILITARY SYSTEM =====================
# ==========================================================

# --------------------- UNIT TYPES -------------------------
print("Creating unit_types table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS unit_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    recruitment_cost INTEGER NOT NULL,
    upkeep_cost INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    defense INTEGER NOT NULL
);
""")
print("Unit types table created successfully.")

# -------------------- COUNTRY UNITS ------------------------
print("Creating country_units table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS country_units (
    country_code TEXT,
    unit_type_id INTEGER,
    amount INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (country_code, unit_type_id),
    FOREIGN KEY (country_code) REFERENCES countries(code),
    FOREIGN KEY (unit_type_id) REFERENCES unit_types(id)
);
""")
print("Country units table created successfully.")

# ==========================================================
# ======================= MODIFIERS ========================
# ==========================================================

# ------------------- MASTER MODIFIER ----------------------
print("Creating master modifier table...")
cursor.execute("""
CREATE TABLE modifiers (
    modifier_key TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    default_value REAL DEFAULT 0
);
""")
print("Master modifiers table created successfully.")

# ------------------- BUILDING EFFECTS ---------------------
print("Creating building effects table...")
cursor.execute("""
CREATE TABLE building_effects (
    building_type TEXT,
    scope TEXT CHECK(scope IN ('province','country')),
    modifier_key TEXT,
    value REAL,
    PRIMARY KEY (building_type, scope, modifier_key),
    FOREIGN KEY (building_type) REFERENCES building_types(building_type),
    FOREIGN KEY (modifier_key) REFERENCES modifiers(modifier_key)
);
""")
print("Building effects table created successfully.")

# ------------------- COUNTRY MODIFIERS ---------------------
print("Creating country modifiers table...")
cursor.execute("""
CREATE TABLE country_modifiers (
    country_code TEXT,
    modifier_key TEXT,
    value REAL DEFAULT 0,
    PRIMARY KEY (country_code, modifier_key),
    FOREIGN KEY (country_code) REFERENCES countries(code),
    FOREIGN KEY (modifier_key) REFERENCES modifiers(modifier_key)
);
""")
print("Country modifiers table created successfully.")

# ------------------- PROVINCE MODIFIERS --------------------
print("Creating province modifiers table...")
cursor.execute("""
CREATE TABLE province_modifiers (
    province_id INTEGER,
    modifier_key TEXT,
    value REAL DEFAULT 0,
    PRIMARY KEY (province_id, modifier_key),
    FOREIGN KEY (province_id) REFERENCES provinces(id),
    FOREIGN KEY (modifier_key) REFERENCES modifiers(modifier_key)
);
""")
print("Province modifiers table created successfully.")

# ------------------- MODIFIER SOURCES ----------------------
print("Creating modifier sources table...")
cursor.execute("""
CREATE TABLE modifier_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT CHECK(scope IN ('province','country')),
    scope_id TEXT,
    modifier_key TEXT,
    value REAL,
    source_type TEXT,
    source_id TEXT
);
""")
print("Modifiers source table created successfully.")

print("✅ All tables have been created")

conn.commit()
conn.close()