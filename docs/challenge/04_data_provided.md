# Data Provided

The dataset contains **5 real buildings** from nuuEnergy projects, provided as CSV + JSON. They are anonymised: no names or addresses, PLZ reduced to area level, floor area and consumption slightly rounded.

- **3 development cases** (`buildings_dev`) carry nuuEnergy's **reference heating-load value** (kW) and the **expected readiness verdict** (green / yellow / red), so teams can build and calibrate their method.

<aside>
🏠

The input fields describe what a homeowner would realistically know. Empty values mean the information was not documented, just like in real life. Some cases are deliberately contradictory.

</aside>

## Download

[buildings_dev.csv](../../data/buildings_dev.csv)

buildings_dev.csv

[buildings_dev.json](../../data/buildings_dev.json)

buildings_dev.json

[buildings_eval.csv](../../data/buildings_eval.csv)

buildings_eval.csv

[buildings_eval.json](../../data/buildings_eval.json)

buildings_eval.json

## The 5 buildings at a glance

| ID | Set | Year | Area | Distribution | Pipe system | Carrier | Consumption | Location |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B-01 | dev | 2001 | 195 m² | radiators | unknown | gas (LPG) | 10,000 kWh | Munich area (82xxx) |
| B-02 | dev | 2005 | 180 m² | underfloor | unknown | gas | 15,500 kWh | Munich area (82xxx) |
| B-03 | dev | 1970 | 200 m² | radiators | two-pipe | oil | 40,000 kWh | Hamburg area (21xxx) |
| B-04 | eval | 1987 | 160 m² | radiators | single-pipe | oil | 25,000 kWh | Munich area (85xxx) |
| B-05 | eval | 2006 | 125 m² | mixed | unknown | gas | 27,000 kWh | Munich area (85xxx) |

Reference values for the dev cases:

| ID | Reference heating load | Expected verdict |
| --- | --- | --- |
| B-01 | 9.6 kW | green |
| B-02 | 9.7 kW | green |
| B-03 | 14.5 kW | yellow |

## Fields

| Field | Type | Example |
| --- | --- | --- |
| building_id | string | B-01 |
| construction_year | integer | 1970 |
| floor_area_m2 | integer | 200 |
| renovation_status | enum (optional, often empty) | unrenovated / partially / fully |
| heat_distribution | enum | radiators / underfloor / mixed |
| annual_consumption_kwh | integer | 24500 |
| energy_carrier | enum | gas / oil / district / electric |
| energy_carrier_detail | string | natural gas / LPG / heating oil, approx. 2,500 litres per year |
| radiator_info | string | 15 radiators, 12 valves need replacement |
| pipe_system | enum ([what is this?](https://app.notion.com/p/Background-Single-pipe-vs-two-pipe-heating-34642d94208e829187118141afb1acf2?pvs=21)) | two-pipe / single-pipe / unknown |
| flow_temperature_c | integer (optional, often empty) | 55 |
| persons_in_household | integer | 3 |
| hot_water_via_heating | boolean | yes / no |
| rooms | integer (optional) | 11 |
| building_notes | string | insulation, extra heat sources (e.g. wood stove), solar thermal |
| location | string (area-level) | Munich area (82xxx) |
| reference_heating_load_kw | number (dev cases only) | 9.6 |
| expected_verdict | enum (dev cases only) | green / yellow / red |