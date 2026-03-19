# tgsimdb - Telegram Simulation Database

`tgsimdb` is an acronym that stands for Telegram Simulation Database. Telegram Simulations (or "SIMs" for short) are text-based turn-based strategy RP games where you take control of an historical nation or state in a given time period, interacting and competing with other players for global domination. Like any other RP game each player starts with a "File" in which they can find all the relevant data that they need in order to play. As the game progresses and players make their moves, that data needs to be constantly updated and player files need to be rewritten each week. That work is usually done manually by the admins/masters of the RPs with the use of text files or excel spreadsheets. This project aims at creating a universal database made with the use of Python and SQLite to manage and automatically update, print and share player files.

This project is in the earliest stages of development. Current version is v.1.1.2

## Table of Contents
1. [Project Overview](#project-overview)
2. [CSV Data Structure](#csv-data-structure)
3. [Data Import Process](#data-import-process)
4. [Available Scripts](#available-scripts)
5. [Usage Examples](#usage-examples)
6. [Future Roadmap](#future-roadmap)

## Project Overview
`tgsimdb` is designed to automate the management of Telegram Simulation games by providing a centralized database system. The project uses Python and SQLite to handle game data, allowing administrators to focus on gameplay rather than manual data management.

## CSV Data Structure
The project uses CSV files to define the initial game state. Each CSV file represents a different aspect of the game world:

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

### Country-Specific Data Import
3. **import_moves.py**: Imports player moves
   - Imports economy data, military units, resources, and modifiers
   - Links data to specific countries

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
- **import_moves.py**: Imports country-specific data and initial moves
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
- **db_utils.py**: Database connection utilities

## Usage Examples

### Setting Up a New Game
```bash
# Initialize the database
python setup_db.py

# Import core game data
python import_data.py

# Import country-specific data
python import_moves.py
```

### Running a Game Turn
```bash
# Process player moves
python process_moves.py

# Update economy
python economy_tick.py

# Export player files
python export.py ROM
python export_it.py ROM
```

### Exporting Player Information
```bash
# Export in English
python export.py ROM

# Export in Italian
python export_it.py ROM
```

## Future Roadmap

### Immediate Goals (v1.1.X)
- [ ] Add support for multiple scenarios
- [ ] Implement conflict resolution system
- [ ] Add diplomatic relations tracking
- [ ] Performance optimization for large games

## Contributing
Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## License
This project is open source and available under the MIT License.

## Support
For support and questions, please refer to the project documentation or create an issue in the repository.