# tgsimdb - Telegram Simulation Database

`tgsimdb` is an acronym that stands for Telegram Simulation Database. Telegram Simulations (or "SIMs" for short) are text-based turn-based strategy RP games where you take control of an historical nation or state in a given time period, interacting and competing with other players for global domination. Like any other RP game each player starts with a "File" in which they can find all the relevant data that they need in order to play. As the game progresses and players make their moves, that data needs to be constantly updated and player files need to be rewritten each week. That work is usually done manually by the admins/masters of the RPs with the use of text files or excel spreadsheets. This project aims at creating a universal database made with the use of Python and SQLite to manage and automatically update, print and share player files.

This project is in the earliest stages of development. Current version is v.1.3.1

## Table of Contents
1. [Project Overview](#project-overview)
2. [CSV Data Structure](#csv-data-structure)
3. [Data Import Process](#data-import-process)
4. [Available Scripts](#available-scripts)
5. [Admin Commands](#admin-commands)
6. [Usage Examples](#usage-examples)
7. [Future Roadmap](#future-roadmap)

## Project Overview
`tgsimdb` is designed to automate the management of Telegram Simulation games by providing a centralized database system. The project uses Python and SQLite to handle game data, allowing administrators to focus on gameplay rather than manual data management.

## CSV Data Structure
The project uses CSV files to define the initial game state. Each CSV file represents a different aspect of the game world:

Scenario data can now be stored inside subfolders under `data/`, for example:

```text
data/
  Diadochi 322 AC/
    countries.csv
    provinces.csv
    resources.csv
    ...
```

Player move files can also be stored inside subfolders under `moves/`, for example:

```text
moves/
  Diadochi 322 AC Partita 1/
    player_moves_turn_1.csv
```
As of now, new scenarios must use the hard coded keys used by economy_tick.py and import_moves.py. In a future update this issue will be addressed to make the project 100% compatible with any scenario that follows the data structure.

### Core Data Files
- **countries.csv**: Defines all countries in the game
  - Fields: code, name, capital, culture, culture_group, religion, government, stability, unrest, corruption, at_war, war_exhaustion
- **provinces.csv**: Defines all provinces in the game
  - Fields: id, name, population, owner_country_code, rank, religion, culture, terrain, is_naval, resource_id
- **resources.csv**: Defines all resources in the game
  - Fields: id, name, description, base_price

### Building Data Files
- **building_types.csv**: Defines all building types
  - Fields: id, name, building_type, base_cost, base_tax_income, base_production, base_upkeep, description
- **building_effects.csv**: Defines building effects on modifiers
  - Fields: building_type_id, scope, modifier_key, value
- **building_resource_cost.csv**: Defines resource costs for buildings
  - Fields: building_type_id, resource_id, amount_per_unit

### Military Data Files
- **unit_types.csv**: Defines all unit types
  - Fields: id, name, unit_category, recruitment_cost, upkeep_cost, attack, defense
- **unit_resource_costs.csv**: Defines resource costs for units
  - Fields: unit_type_id, resource_id, amount_per_unit

### Country-Specific Data Files
- **country_economy.csv**: Economic data for each country
  - Fields: country_code, treasury, tax_rate, tax_income, building_income, total_income, administration_cost, building_upkeep, military_upkeep, total_expenses, tax_efficiency, economic_growth, total_population
- **country_units.csv**: Military units for each country
  - Fields: country_code, unit_type_id, amount
- **country_resources.csv**: Resource stockpiles for each country
  - Fields: country_code, resource_id, stockpile
- **country_modifiers.csv**: Country-specific modifiers
  - Fields: country_code, modifier_key, value

## Data Import Process
The import process is handled by several scripts that work together to populate the database:

### Initial Setup
1. **setup_db.py**: Creates the database schema and all necessary tables
2. **import_data.py**: Imports core data from CSV files
   - Imports countries, provinces, resources, building types, and unit types
   - Establishes relationships between tables
   - Can load from `data/<scenario_name>/` when a scenario subfolder is provided

### Country-Specific Data Import
3. **import_moves.py**: Imports player moves
   - Imports economy data, military units, resources, and modifiers
   - Links data to specific countries
   - Can load from `moves/<moves_subfolder>/` when a moves subfolder is provided

### Game Management
4. **process_moves.py**: Processes player moves each turn
   - Updates database based on player actions
   - Handles building construction, unit recruitment, trade, etc.

### Economy Management
5. **economy_tick.py**: Updates economy each turn
   - Calculates income, expenses, and economic changes
   - Updates country treasuries and populations

## Available Scripts

### Data Management Scripts
- **setup_db.py**: Initializes the database with all tables
- **import_data.py**: Imports core game data from CSV files
  - Usage: `python import_data.py [scenario_subfolder]`
- **import_moves.py**: Imports country-specific data and initial moves
  - Usage: `python import_moves.py <turn_number> [moves_subfolder]`
- **process_moves.py**: Processes player moves and updates database
- **economy_tick.py**: Updates economic data each turn

### Export Scripts
- **export_en.py**: Exports country information in English
  - Usage: `python export_en.py <country_code>`
  - Creates files/ROM 12-03-2026 16-41.txt
- **export_it.py**: Exports country information in Italian
  - Usage: `python export_it.py <country_code>`
  - Creates files/ROM 12-03-2026 16-49.txt.txt`

### Utility Scripts
- **balance_report.py**: Generates economic balance reports
- **admin_tools.py**: Applies admin/event changes safely and logs them to `event_log`
- **db_utils.py**: Database connection utilities

## Admin Commands

`admin_tools.py` is the recommended way to apply mid-game event changes instead of editing SQL rows manually. It validates the requested change, updates the relevant tables, logs the change in `event_log`, and refreshes derived `country_economy` values when needed.

### Supported Commands
- `python admin_tools.py set-basic <country_code> <field> <value>`
  - Allowed fields: `capital`, `government`, `culture`, `culture_group`, `religion`
- `python admin_tools.py set-political <country_code> <field> <value>`
  - Allowed fields: `stability`, `unrest`, `corruption`, `war_exhaustion`, `at_war`
- `python admin_tools.py add-treasury <country_code> <amount>`
- `python admin_tools.py remove-treasury <country_code> <amount>`
- `python admin_tools.py set-tax-rate <country_code> <tax_rate>`
- `python admin_tools.py add-food <country_code> <resource_name> <amount>`
- `python admin_tools.py remove-food <country_code> <resource_name> <amount>`
- `python admin_tools.py transfer-province <province_id> <target_country_code>`
- `python admin_tools.py change-population <province_id> <delta>`
- `python admin_tools.py spawn-units <country_code> <unit_name_or_id> <amount>`
- `python admin_tools.py add-building <province_id> <building_name_or_id> <amount>`
- `python admin_tools.py set-modifier <country_code> <modifier_key> <value>`
- `python admin_tools.py add-modifier <country_code> <modifier_key> <delta>`
- `python admin_tools.py remove-modifier <country_code> <modifier_key>`
- `python admin_tools.py refresh-country <country_code>`
- `python admin_tools.py refresh-all`

### Event Log

Each admin command writes one or more rows to the `event_log` table. Logged values include:
- command name
- target table and target key
- field changed
- old value
- new value
- numeric delta when applicable
- notes about why the refresh happened

This makes it easier to audit manual/event-driven changes during a campaign.

## Usage Examples

### Setting Up a New Game
```bash
# Initialize the database
python setup_db.py

# Import a specific scenario from data/<scenario_subfolder>
python import_data.py "Diadochi 322 AC"

# Import turn 1 moves from moves/<moves_subfolder>
python import_moves.py 1 "Diadochi 322 AC Partita 1"
```

If you still keep files directly in the root `data/` or `moves/` folders, both scripts remain backward-compatible:

```bash
python import_data.py
python import_moves.py 1
```

### Running a Game Turn
```bash
# Process player moves
python process_moves.py

# Update economy
python economy_tick.py

# Export player files
python export_en.py ROM
python export_it.py ROM
```

### Exporting Player Information
```bash
# Export in English
python export_en.py ROM

# Export in Italian
python export_it.py ROM
```

### Applying Admin/Event Changes
```bash
# Add treasury after an event
python admin_tools.py add-treasury ROM 200

# Change a country's religion
python admin_tools.py set-basic ROM religion Hellenic

# Increase unrest after a rebellion
python admin_tools.py set-political ROM unrest 12

# Add emergency food reserves
python admin_tools.py add-food ROM grain 10

# Transfer a province after a war
python admin_tools.py transfer-province 17 CAR

# Recalculate derived economy values
python admin_tools.py refresh-country ROM
python admin_tools.py refresh-all
```

## Contributing
Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## License
This project is open source and available under the GPL v3 License.

## Support
For support and questions, please refer to the project documentation or create an issue in the repository.
