from db_utils import get_connection
import csv
from collections import defaultdict

def process_building_effects():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Read building effects
    building_effects = {}
    with open('data/building_effects.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_name = row['building_name']
            scope = row['scope']
            modifier_key = row['modifier_key']
            value = float(row['value'])
            building_effects.setdefault((building_name, scope, modifier_key), []).append(value)
    
    # Read province buildings to map buildings to countries
    building_to_country = defaultdict(lambda: defaultdict(int))
    with open('data/province_buildings.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            province_name = row['province_name']
            building_name = row['building_name']
            amount = int(row['amount'])
            
            # Get province ID
            cursor.execute("SELECT id FROM provinces WHERE name = ?", (province_name,))
            province_id = cursor.fetchone()
            if not province_id:
                continue
            province_id = province_id[0]
            
            # Get owner country
            cursor.execute("SELECT owner_country_code FROM provinces WHERE id = ?", (province_id,))
            result = cursor.fetchone()
            if not result:
                continue
            country_code = result[0]
            
            # Accumulate building amounts per country
            building_to_country[country_code][building_name] += amount
    
    # Aggregate building effects into country modifiers
    country_modifiers = defaultdict(lambda: defaultdict(float))
    for (building_name, scope, modifier_key), values in building_effects.items():
        for value in values:
            # Get total amount of this building across all provinces
            total_amount = 0
            for country_code, buildings in building_to_country.items():
                if building_name in buildings:
                    total_amount += buildings[building_name]
            
            # Apply amount multiplier to effect value
            aggregated_value = value * total_amount
            
            # Store in country_modifiers
            for country_code in building_to_country:
                if any(building in buildings for building in building_to_country[country_code] if building == building_name):
                    country_modifiers[country_code][modifier_key] += aggregated_value
    
    # Insert into country_modifiers table
    for country_code, modifiers in country_modifiers.items():
        for modifier_key, value in modifiers.items():
            cursor.execute("""
                INSERT OR REPLACE INTO country_modifiers (country_code, modifier_key, value)
                VALUES (?, ?, ?)
            """, (country_code, modifier_key, value))
    
    conn.commit()
    conn.close()
    print("✅ Building effects processed successfully")

if __name__ == "__main__":
    process_building_effects()