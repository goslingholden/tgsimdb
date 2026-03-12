from db_utils import get_connection

conn = get_connection()
cursor = conn.cursor()
conn.execute("PRAGMA foreign_keys = ON;")


print("Building nations...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS countries (
    code TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    capital TEXT NOT NULL DEFAULT 'Unknown',
    culture TEXT NOT NULL DEFAULT 'Unknown',
    culture_group TEXT NOT NULL DEFAULT 'Unknown',
    religion TEXT NOT NULL DEFAULT 'Unknown',
    government TEXT NOT NULL DEFAULT 'Unknown',
    stability INTEGER NOT NULL DEFAULT 50,
    unrest INTEGER NOT NULL DEFAULT 0,
    corruption REAL NOT NULL DEFAULT 0.0,
    at_war INTEGER NOT NULL DEFAULT 0,
    war_exhaustion INTEGER NOT NULL DEFAULT 0
);
""")
print("Nation-building completed.")


print("Creating resources table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    base_price INTEGER DEFAULT 1
);
""")
print("Resources table created successfully.")


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
    is_naval REAL NOT NULL DEFAULT 0,
    resource_id INTEGER,
    FOREIGN KEY (owner_country_code) REFERENCES countries(code),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);
""")
print("Provinces table created successfully.")


print("Creating building_types table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS building_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    building_type TEXT NOT NULL,
    base_cost INTEGER NOT NULL,
    base_tax_income INTEGER NOT NULL DEFAULT 0,
    base_production INTEGER NOT NULL DEFAULT 0,
    base_upkeep INTEGER NOT NULL DEFAULT 0,
    description TEXT
);
""")
print("Building types table created successfully.")


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


print("Creating country_economy table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS country_economy (
    country_code TEXT PRIMARY KEY,
    treasury INTEGER NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.1,
    tax_income INTEGER NOT NULL DEFAULT 0,
    building_income INTEGER NOT NULL DEFAULT 0,
    total_income INTEGER NOT NULL DEFAULT 0,
    administration_cost INTEGER NOT NULL DEFAULT 0,
    building_upkeep INTEGER NOT NULL DEFAULT 0,
    military_upkeep INTEGER NOT NULL DEFAULT 0,
    total_expenses INTEGER NOT NULL DEFAULT 0,
    tax_efficiency REAL NOT NULL DEFAULT 1.0,
    economic_growth REAL NOT NULL DEFAULT 0.0,
    total_population INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (country_code) REFERENCES countries(code)
);
""")
print("Country economy table created successfully.")


print("Creating unit_types table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS unit_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    unit_category TEXT NOT NULL,
    recruitment_cost INTEGER NOT NULL,
    upkeep_cost INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    defense INTEGER NOT NULL
);
""")
print("Unit types table created successfully.")


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


print("Creating master modifier table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS modifiers (
    modifier_key TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    default_value REAL DEFAULT 1.0
);
""")
print("Master modifiers table created successfully.")


print("Creating building effects table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS building_effects (
    building_type_id INTEGER,
    scope TEXT CHECK(scope IN ('province','country')),
    modifier_key TEXT,
    value REAL,
    PRIMARY KEY (building_type_id, scope, modifier_key),
    FOREIGN KEY (building_type_id) REFERENCES building_types(id),
    FOREIGN KEY (modifier_key) REFERENCES modifiers(modifier_key)
);
""")
print("Building effects table created successfully.")


print("Creating country modifiers table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS country_modifiers (
    country_code TEXT,
    modifier_key TEXT,
    value REAL DEFAULT 0,
    PRIMARY KEY (country_code, modifier_key),
    FOREIGN KEY (country_code) REFERENCES countries(code),
    FOREIGN KEY (modifier_key) REFERENCES modifiers(modifier_key)
);
""")
print("Country modifiers table created successfully.")


print("Creating country_resources table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS country_resources (
    country_code TEXT NOT NULL,
    resource_id INTEGER NOT NULL,
    stockpile INTEGER DEFAULT 0,
    PRIMARY KEY (country_code, resource_id),
    FOREIGN KEY (country_code) REFERENCES countries(code),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);
""")
print("Country resources table created successfully.")


print("Creating building resource costs table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS building_resource_costs (
    building_type_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    amount_per_unit INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (building_type_id, resource_id),
    FOREIGN KEY (building_type_id) REFERENCES building_types(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);
""")
print("Building resource costs table created successfully.")


print("Creating unit resource costs table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS unit_resource_costs (
    unit_type_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    amount_per_unit INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (unit_type_id, resource_id),
    FOREIGN KEY (unit_type_id) REFERENCES unit_types(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);
""")
print("Unit resource costs table created successfully.")


print("Creating player_moves table...")
cursor.execute("""
CREATE TABLE IF NOT EXISTS player_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn INTEGER NOT NULL,
    country_code TEXT NOT NULL,
    move_type TEXT NOT NULL,              
    target_province_id INTEGER,
    target_building_type_id INTEGER,
    target_unit_type_id INTEGER,
    target_country_code TEXT,
    target_resource_id INTEGER,
    trade_resource_id INTEGER,
    price_per_unit INTEGER DEFAULT 0,
    amount INTEGER DEFAULT 1,
    notes TEXT,
    processed BOOLEAN DEFAULT 0,
    error_message TEXT,

    FOREIGN KEY (country_code) REFERENCES countries(code),
    FOREIGN KEY (target_province_id) REFERENCES provinces(id),
    FOREIGN KEY (target_building_type_id) REFERENCES building_types(id),
    FOREIGN KEY (target_unit_type_id) REFERENCES unit_types(id),
    FOREIGN KEY (target_country_code) REFERENCES countries(code),
    FOREIGN KEY (target_resource_id) REFERENCES resources(id),
    FOREIGN KEY (trade_resource_id) REFERENCES resources(id)
);
""")
print("Player moves table created successfully.")


cursor.execute("PRAGMA table_info(player_moves)")
player_move_columns = {row[1] for row in cursor.fetchall()}

if "target_country_code" not in player_move_columns:
    cursor.execute("ALTER TABLE player_moves ADD COLUMN target_country_code TEXT")
if "target_resource_id" not in player_move_columns:
    cursor.execute("ALTER TABLE player_moves ADD COLUMN target_resource_id INTEGER")
if "trade_resource_id" not in player_move_columns:
    cursor.execute("ALTER TABLE player_moves ADD COLUMN trade_resource_id INTEGER")
if "price_per_unit" not in player_move_columns:
    cursor.execute("ALTER TABLE player_moves ADD COLUMN price_per_unit INTEGER DEFAULT 0")

print("✅ All tables have been created")

conn.commit()
conn.close()
