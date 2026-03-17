#!/usr/bin/env python3
"""
Esporta tutte le informazioni su un paese in un file di testo leggibile.

Uso: python export_it.py <codice_paese>
Esempio: python export_it.py ROM
"""

import sys
import os
from datetime import datetime
from db_utils import get_connection
from economy_tick import get_land_unit_cap, get_navy_unit_cap


GOVERNMENT_TRANSLATIONS = {
    "monarchy": "Monarchia",
    "republic": "Repubblica",
    "tribe": "Tribù",
}

RANK_TRANSLATIONS = {
    "city": "Città",
    "settlement": "Insediamento",
}

TERRAIN_TRANSLATIONS = {
    "desert": "Deserto",
    "farmland": "Campi coltivati",
    "farmlands": "Campi coltivati",
    "forest": "Foresta",
    "hills": "Colline",
    "marsh": "Palude",
    "mountains": "Montagne",
    "plains": "Pianure",
}

RESOURCE_TRANSLATIONS = {
    "base_metals": "Metalli comuni",
    "cloth": "Stoffa",
    "dyes": "Tinture",
    "earthenware": "Terracotta",
    "elephants": "Elefanti",
    "glass": "Vetro",
    "grain": "Grano",
    "honey": "Miele",
    "horses": "Cavalli",
    "iron": "Ferro",
    "leather": "Cuoio",
    "livestock": "Bestiame",
    "marble": "Marmo",
    "olives": "Olive",
    "precious_metals": "Metalli preziosi",
    "salt": "Sale",
    "slaves": "Schiavi",
    "stone": "Pietra",
    "wine": "Vino",
    "wood": "Legname",
}

MODIFIER_DESCRIPTION_TRANSLATIONS = {
    "Administrative cost multiplier": "Moltiplicatore dei costi amministrativi",
    "Administration cost reduction": "Riduzione dei costi amministrativi",
    "Corruption level affecting tax collection": "Livello di corruzione che influisce sulla riscossione fiscale",
    "corruption reduction": "Riduzione della corruzione",
    "Mil bonus": "Bonus militare",
    "Economic growth rate": "Tasso di crescita economica",
    "Additional land unit capacity": "Capacità aggiuntiva per unità terrestri",
    "Military unit cap multiplier": "Moltiplicatore del limite delle unità militari",
    "Military upkeep multiplier": "Moltiplicatore del mantenimento militare",
    "Additional navy unit capacity": "Capacità aggiuntiva per unità navali",
    "Navy upkeep modifier": "Modificatore del mantenimento navale",
    "Rate of pop growth per turn": "Tasso di crescita della popolazione per turno",
    "Adds production of base metals": "Aggiunge produzione di metalli comuni",
    "Adds production of cloth": "Aggiunge produzione di stoffa",
    "Adds production of grain": "Aggiunge produzione di grano",
    "Adds production of honey": "Aggiunge produzione di miele",
    "Adds production of iron": "Aggiunge produzione di ferro",
    "Adds production of livestock": "Aggiunge produzione di bestiame",
    "Adds production of olives": "Aggiunge produzione di olive",
    "Adds production of slaves": "Aggiunge produzione di schiavi",
    "Adds production of stone": "Aggiunge produzione di pietra",
    "Adds production of wine": "Aggiunge produzione di vino",
    "Adds production of wood": "Aggiunge produzione di legname",
    "Province production multiplier": "Moltiplicatore della produzione provinciale",
    "Additional resource cap": "Capacità aggiuntiva di risorse",
    "Stability growth per turn": "Crescita della stabilità per turno",
    "Tax income multiplier": "Moltiplicatore delle entrate fiscali",
    "Unrest reduction per turn": "Riduzione dei disordini per turno",
}


def translate_value(value, translations):
    return translations.get(value, value)

def format_number(num):
    """Formatta i numeri con le virgole per leggibilità."""
    return f"{num:,}" if isinstance(num, (int, float)) else str(num)

def get_country_info(conn, country_code):
    """Recupera tutte le informazioni su un paese dal database."""
    cursor = conn.cursor()
    
    # Ottieni informazioni di base sul paese
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
    
    # Ottieni dati economici
    cursor.execute("SELECT * FROM country_economy WHERE country_code = ?", (country_code,))
    economy = cursor.fetchone()
    if economy:
        columns = [desc[0] for desc in cursor.description]
        country_data['economy'] = dict(zip(columns, economy))
    
    # Ottieni unità militari
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
    
    # Ottieni risorse e scorte
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
    
    # Ottieni modificatori
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
    
    # Ottieni province
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
        lines.append("  Nessuna")
        lines.append("")
        return

    for unit in units:
        upkeep = unit['amount'] * unit['upkeep_cost']
        total_upkeep += upkeep
        lines.append(f"  {unit['name']}: {format_number(unit['amount'])} unità")
        lines.append(
            f"    Costo Reclutamento: {format_number(unit['recruitment_cost'])} | "
            f"Manutenzione per unità: {format_number(unit['upkeep_cost'])} | "
            f"Manutenzione Totale: {format_number(upkeep)}"
        )
    lines.append(f"Manutenzione Totale: {format_number(total_upkeep)}")
    lines.append("")

def generate_report(country_data):
    """Genera un report leggibile da dati del paese."""
    lines = []
    
    # Intestazione
    lines.append("=" * 60)
    lines.append(f"INFORMAZIONI PAESE: {country_data['name']} ({country_data['code']})")
    lines.append("=" * 60)
    lines.append("")
    
    # Informazioni di base
    lines.append("INFORMAZIONI DI BASE")
    lines.append("-" * 40)
    lines.append(f"Capitale:        {country_data['capital']}")
    lines.append(f"Governo:         {translate_value(country_data['government'], GOVERNMENT_TRANSLATIONS)}")
    lines.append(f"Cultura:         {country_data['culture']}")
    lines.append(f"Gruppo Culturale: {country_data['culture_group']}")
    lines.append(f"Religione:       {country_data['religion']}")
    lines.append("")
    
    # Stato
    lines.append("STATO")
    lines.append("-" * 40)
    lines.append(f"Stabilità:       {country_data['stability']}")
    lines.append(f"Disordini:       {country_data['unrest']}")
    lines.append(f"Corruzione:      {country_data['corruption']}")
    lines.append(f"In Guerra:       {'Sì' if country_data['at_war'] else 'No'}")
    lines.append(f"Esaurimento Bellico: {country_data['war_exhaustion']}")
    lines.append("")
    
    # Economia
    if 'economy' in country_data and country_data['economy']:
        econ = country_data['economy']
        lines.append("ECONOMIA")
        lines.append("-" * 40)
        lines.append(f"Cassa:                  {format_number(econ.get('treasury', 0))}")
        lines.append(f"Popolazione Totale:     {format_number(econ.get('total_population', 0))}")
        lines.append("")
        lines.append("Entrate:")
        lines.append(f"  Imposte:              {format_number(econ.get('tax_income', 0))}")
        lines.append(f"  Entrate Edilizie:     {format_number(econ.get('building_income', 0))}")
        lines.append(f"  Entrate Totali:       {format_number(econ.get('total_income', 0))}")
        lines.append("")
        lines.append("Spese:")
        lines.append(f"  Costi Amministrativi: {format_number(econ.get('administration_cost', 0))}")
        lines.append(f"  Manutenzione Edifici: {format_number(econ.get('building_upkeep', 0))}")
        lines.append(f"  Manutenzione Militare: {format_number(econ.get('military_upkeep', 0))}")
        lines.append(f"  Spese Totali:         {format_number(econ.get('total_expenses', 0))}")
        lines.append("")
        net_income = econ.get('total_income', 0) - econ.get('total_expenses', 0)
        lines.append(f"Entrate Nette:          {format_number(net_income)}")
        lines.append("")
    
    # Militare
    if country_data['units']:
        land_units = [unit for unit in country_data['units'] if unit['category'] == 'land']
        naval_units = [unit for unit in country_data['units'] if unit['category'] == 'naval']
        lines.append("FORZE ARMATE")
        lines.append("-" * 40)
        lines.append("")
        append_unit_section(lines, "FORZE DI TERRA", land_units, "Limite unità terrestri", country_data['land_unit_cap'])
        append_unit_section(lines, "FORZE NAVALI", naval_units, "Limite unità navali", country_data['navy_unit_cap'])
    
    # Risorse
    if country_data['resources']:
        lines.append("RISORSE")
        lines.append("-" * 40)
        for res in country_data['resources']:
            lines.append(f"  {translate_value(res['name'], RESOURCE_TRANSLATIONS)}: {format_number(res['stockpile'])}")
        lines.append("")
    
    # Modificatori
    if country_data['modifiers']:
        lines.append("MODIFICATORI")
        lines.append("-" * 40)
        for mod in country_data['modifiers']:
            value_str = f"{mod['value']:+.2f}" if isinstance(mod['value'], (int, float)) else str(mod['value'])
            lines.append(f"  {mod['key']}: {value_str}")
            lines.append(f"    {translate_value(mod['description'], MODIFIER_DESCRIPTION_TRANSLATIONS)}")
        lines.append("")
    
    # Province
    if country_data['provinces']:
        total_pop = sum(p['population'] for p in country_data['provinces'])
        lines.append("PROVINCE")
        lines.append("-" * 40)
        lines.append(f"Province Totali: {len(country_data['provinces'])} | Popolazione Totale: {format_number(total_pop)}")
        lines.append("")
        for i, prov in enumerate(country_data['provinces'], 1):
            naval_str = " (Navale)" if prov['is_naval'] else ""
            lines.append(f"{i}. {prov['name']}{naval_str}")
            lines.append(f"   Popolazione: {format_number(prov['population'])} | Grado: {translate_value(prov['rank'], RANK_TRANSLATIONS)}")
            lines.append(f"   Cultura: {prov['culture']} | Religione: {prov['religion']}")
            lines.append(f"   Terreno: {translate_value(prov['terrain'], TERRAIN_TRANSLATIONS)}")
            lines.append("")
    
    lines.append("=" * 60)
    lines.append(f"Report generato per {country_data['name']} ({country_data['code']})")
    lines.append("=" * 60)
    
    return "\n".join(lines)

def main():
    if len(sys.argv) != 2:
        print("Uso: python export_it.py <codice_paese>")
        print("Esempio: python export_it.py ROM")
        sys.exit(1)
    
    country_code = sys.argv[1].upper()
    
    try:
        conn = get_connection()
        country_data = get_country_info(conn, country_code)
        conn.close()
        
        if not country_data:
            print(f"Errore: Paese con codice '{country_code}' non trovato.")
            sys.exit(1)
        
        report = generate_report(country_data)
        
        # Crea cartella 'files' se non esiste
        files_dir = "files"
        os.makedirs(files_dir, exist_ok=True)
        
        # Genera nome file con formato data italiano (usando caratteri sicuri)
        now = datetime.now()
        date_str = now.strftime("%d-%m-%Y %H-%M")
        filename = f"{country_code} {date_str}.txt"
        filepath = os.path.join(files_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"Esportazione completata per {country_data['name']} in {filepath}")
        
    except Exception as e:
        print(f"Errore: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
