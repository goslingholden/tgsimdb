#!/usr/bin/env python3
"""
Export all information about a country to a human-readable text file.

Usage: python export.py <country_code>
Example: python export.py ROM
"""

import sys
import os
from datetime import datetime
from db_utils import get_connection
from economy_tick import get_land_unit_cap, get_navy_unit_cap

def format_number(num):
    """Format numbers with commas for readability."""
    return f"{num:,}" if isinstance(num, (int, float)) else str(num)

def get_country_info(conn, country_code):
    """Fetch all information about a country from the database."""
    cursor = conn.cursor()
    
    # Get basic country info
    cursor.execute("""
        SELECT code, name, capital, culture, culture_group, religion,
               government, stability, unrest, corruption, at_war, war_exhaustion
        FROM countries
        WHERE code = ?
    """, (country_code,))
    
    country = cursor.fetchone()
    if not country:
        return None
    
    country_data = {
        'code': country[0],
        'name': country[1],
        'capital': country[2],
        'culture': country[3],
        'culture_group': country[4],
        'religion': country[5],
        'government': country[6],
        'stability': country[7],
        'unrest': country[8],
        'corruption': country[9],
        'at_war': bool(country[10]),
        'war_exhaustion': country[11]
    }
    
    # Get economic data
    cursor.execute("SELECT * FROM country_economy WHERE country_code = ?", (country_code,))
    economy = cursor.fetchone()
    if economy:
        columns = [desc[0] for desc in cursor.description]
        country_data['economy'] = dict(zip(columns, economy))
    
    # Get military units
    cursor.execute("""
        SELECT ut.name, ut.unit_category, cu.amount, ut.recruitment_cost, ut.upkeep_cost
        FROM country_units cu
        JOIN unit_types ut ON cu.unit_type_id = ut.id
        WHERE cu.country_code = ?
        ORDER BY ut.name
    """, (country_code,))
    
    units = cursor.fetchall()
    country_data['units'] = []
    for unit in units:
        country_data['units'].append({
            'name': unit[0],
            'category': unit[1],
            'amount': unit[2],
            'recruitment_cost': unit[3],
            'upkeep_cost': unit[4]
        })
    
    # Get resources and stockpiles
    cursor.execute("""
        SELECT r.name, cr.stockpile
        FROM country_resources cr
        JOIN resources r ON cr.resource_id = r.id
        WHERE cr.country_code = ?
        ORDER BY r.name
    """, (country_code,))
    
    resources = cursor.fetchall()
    country_data['resources'] = []
    for res in resources:
        country_data['resources'].append({
            'name': res[0],
            'stockpile': res[1]
        })
    
    # Get modifiers
    cursor.execute("""
        SELECT m.modifier_key, cm.value, m.description
        FROM country_modifiers cm
        JOIN modifiers m ON cm.modifier_key = m.modifier_key
        WHERE cm.country_code = ?
        ORDER BY m.modifier_key
    """, (country_code,))
    
    modifiers = cursor.fetchall()
    country_data['modifiers'] = []
    for mod in modifiers:
        country_data['modifiers'].append({
            'key': mod[0],
            'value': mod[1],
            'description': mod[2]
        })
    
    # Get provinces
    cursor.execute("""
        SELECT name, population, rank, religion, culture, terrain, is_naval
        FROM provinces
        WHERE owner_country_code = ?
        ORDER BY name
    """, (country_code,))
    
    provinces = cursor.fetchall()
    country_data['provinces'] = []
    for prov in provinces:
        country_data['provinces'].append({
            'name': prov[0],
            'population': prov[1],
            'rank': prov[2],
            'religion': prov[3],
            'culture': prov[4],
            'terrain': prov[5],
            'is_naval': bool(prov[6])
        })
    
    country_data['land_unit_cap'] = get_land_unit_cap(cursor, country_code)
    country_data['navy_unit_cap'] = get_navy_unit_cap(cursor, country_code)

    return country_data


def append_unit_section(lines, title, units, cap_label, unit_cap):
    lines.append(title)
    lines.append("-" * 40)
    total_units = sum(unit['amount'] for unit in units)
    total_upkeep = 0
    lines.append(f"{cap_label}: {format_number(total_units)} / {format_number(unit_cap)}")
    lines.append("")

    if not units:
        lines.append("  None")
        lines.append("")
        return

    for unit in units:
        upkeep = unit['amount'] * unit['upkeep_cost']
        total_upkeep += upkeep
        lines.append(f"  {unit['name']}: {format_number(unit['amount'])} units")
        lines.append(
            f"    Recruitment Cost: {format_number(unit['recruitment_cost'])} | "
            f"Upkeep per unit: {format_number(unit['upkeep_cost'])} | "
            f"Total Upkeep: {format_number(upkeep)}"
        )
    lines.append(f"Total Upkeep: {format_number(total_upkeep)}")
    lines.append("")

def generate_report(country_data):
    """Generate a human-readable report from country data."""
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append(f"COUNTRY INFORMATION: {country_data['name']} ({country_data['code']})")
    lines.append("=" * 60)
    lines.append("")
    
    # Basic Information
    lines.append("BASIC INFORMATION")
    lines.append("-" * 40)
    lines.append(f"Capital:        {country_data['capital']}")
    lines.append(f"Government:     {country_data['government']}")
    lines.append(f"Culture:        {country_data['culture']}")
    lines.append(f"Culture Group:  {country_data['culture_group']}")
    lines.append(f"Religion:       {country_data['religion']}")
    lines.append("")
    
    # Status
    lines.append("STATUS")
    lines.append("-" * 40)
    lines.append(f"Stability:      {country_data['stability']}")
    lines.append(f"Unrest:         {country_data['unrest']}")
    lines.append(f"Corruption:     {country_data['corruption']}")
    lines.append(f"At War:         {'Yes' if country_data['at_war'] else 'No'}")
    lines.append(f"War Exhaustion: {country_data['war_exhaustion']}")
    lines.append("")
    
    # Economy
    if 'economy' in country_data and country_data['economy']:
        econ = country_data['economy']
        lines.append("ECONOMY")
        lines.append("-" * 40)
        lines.append(f"Treasury:               {format_number(econ.get('treasury', 0))}")
        lines.append(f"Total Population:       {format_number(econ.get('total_population', 0))}")
        lines.append("")
        lines.append("Income:")
        lines.append(f"  Tax Income:           {format_number(econ.get('tax_income', 0))}")
        lines.append(f"  Building Income:      {format_number(econ.get('building_income', 0))}")
        lines.append(f"  Total Income:         {format_number(econ.get('total_income', 0))}")
        lines.append("")
        lines.append("Expenses:")
        lines.append(f"  Administration Cost:  {format_number(econ.get('administration_cost', 0))}")
        lines.append(f"  Building Upkeep:      {format_number(econ.get('building_upkeep', 0))}")
        lines.append(f"  Military Upkeep:      {format_number(econ.get('military_upkeep', 0))}")
        lines.append(f"  Total Expenses:       {format_number(econ.get('total_expenses', 0))}")
        lines.append("")
        net_income = econ.get('total_income', 0) - econ.get('total_expenses', 0)
        lines.append(f"Net Income:             {format_number(net_income)}")
        lines.append("")
    
    # Military
    if country_data['units']:
        land_units = [unit for unit in country_data['units'] if unit['category'] == 'land']
        naval_units = [unit for unit in country_data['units'] if unit['category'] == 'naval']
        lines.append("MILITARY")
        lines.append("-" * 40)
        lines.append("")
        append_unit_section(lines, "LAND FORCES", land_units, "Land Unit Cap", country_data['land_unit_cap'])
        append_unit_section(lines, "NAVAL FORCES", naval_units, "Naval Unit Cap", country_data['navy_unit_cap'])
    
    # Resources
    if country_data['resources']:
        lines.append("RESOURCES")
        lines.append("-" * 40)
        for res in country_data['resources']:
            lines.append(f"  {res['name']}: {format_number(res['stockpile'])}")
        lines.append("")
    
    # Modifiers
    if country_data['modifiers']:
        lines.append("MODIFIERS")
        lines.append("-" * 40)
        for mod in country_data['modifiers']:
            value_str = f"{mod['value']:+.2f}" if isinstance(mod['value'], (int, float)) else str(mod['value'])
            lines.append(f"  {mod['key']}: {value_str}")
            lines.append(f"    {mod['description']}")
        lines.append("")
    
    # Provinces
    if country_data['provinces']:
        total_pop = sum(p['population'] for p in country_data['provinces'])
        lines.append("PROVINCES")
        lines.append("-" * 40)
        lines.append(f"Total Provinces: {len(country_data['provinces'])} | Total Population: {format_number(total_pop)}")
        lines.append("")
        for i, prov in enumerate(country_data['provinces'], 1):
            naval_str = " (Naval)" if prov['is_naval'] else ""
            lines.append(f"{i}. {prov['name']}{naval_str}")
            lines.append(f"   Population: {format_number(prov['population'])} | Rank: {prov['rank']}")
            lines.append(f"   Culture: {prov['culture']} | Religion: {prov['religion']}")
            lines.append(f"   Terrain: {prov['terrain']}")
            lines.append("")
    
    lines.append("=" * 60)
    lines.append(f"Report generated for {country_data['name']} ({country_data['code']})")
    lines.append("=" * 60)
    
    return "\n".join(lines)

def main():
    if len(sys.argv) != 2:
        print("Usage: python export.py <country_code>")
        print("Example: python export.py ROM")
        sys.exit(1)
    
    country_code = sys.argv[1].upper()
    
    try:
        conn = get_connection()
        country_data = get_country_info(conn, country_code)
        conn.close()
        
        if not country_data:
            print(f"Error: Country with code '{country_code}' not found.")
            sys.exit(1)
        
        report = generate_report(country_data)
        
        # Create 'files' directory if it doesn't exist
        files_dir = "files"
        os.makedirs(files_dir, exist_ok=True)
        
        # Generate filename with European date format (using safe characters)
        now = datetime.now()
        date_str = now.strftime("%d-%m-%Y %H-%M")
        filename = f"{country_code} {date_str}.txt"
        filepath = os.path.join(files_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"Successfully exported {country_data['name']} information to {filepath}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
