"""Deterministic corpus builder: generates the bundled HVAC service-manual chapters.

Writes ~15 markdown chapters for two fictional units:

- AriaTherm X200 air-to-water heat pump (R32, inverter scroll, hydronic)
- VeyraCool V9 air-cooled chiller (R513A, twin-scroll, glycol loop)

Every byte is a pure function of the static data below -- no randomness, no
timestamps, no locale dependence -- so re-running the script is hash-stable
(asserted by the test suite). The generated output is committed to ``corpus/``;
regenerate only when the fictional fleet changes::

    python -m hvac_copilot.scripts.build_corpus --out corpus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------- X200 data ---

X200_FAULT_ROWS: list[tuple[str, str, str, str, str, str]] = [
    # code, display, symptom, likely cause, corrective action, severity
    ("E01", "LOW PRES", "Low suction pressure alarm; compressor cycles off",
     "Refrigerant undercharge, evaporator airflow restriction, or expansion valve stuck closed",
     "Verify airflow (filter/indoor coil), check superheat at service ports; if charge is low, recover and weigh in per Chapter 5", "High"),
    ("E02", "HIGH PRES", "High discharge pressure trip",
     "Condenser fouling, outdoor fan failure, non-condensables in circuit, overcharge",
     "Clean condenser coil, verify outdoor fan operation, check for non-condensables, verify charge by subcooling", "High"),
    ("E03", "OVC", "Compressor overcurrent trip",
     "High discharge pressure, supply voltage out of range, failing compressor bearings",
     "Measure running current against nameplate RLA; check supply voltage within ±10%; inspect compressor if current is high at normal pressures", "High"),
    ("E04", "ICE", "Evaporator coil iced; reduced heating capacity",
     "Low airflow (dirty filter, failed indoor fan) or low refrigerant charge",
     "Inspect and clean filter and indoor coil; verify fan runs at rated speed; check subcooling per Chapter 6 Section 5.4", "Medium"),
    ("E05", "FLOW", "No or low hydronic water flow",
     "Closed isolating valve, blocked Y-strainer, failed circulator pump, airlock",
     "Check valve positions, clean Y-strainer, bleed the hydraulic circuit, measure pump differential pressure", "High"),
    ("E06", "SNT", "Supply water sensor fault (open/short circuit)",
     "Disconnected or damaged NTC sensor, faulty harness",
     "Measure sensor resistance against the NTC table in Chapter 4; replace sensor if outside tolerance", "Low"),
    ("E07", "SNR", "Return water sensor fault (open/short circuit)",
     "Disconnected or damaged NTC sensor, faulty harness",
     "As E06; verify connector seating at terminal X4 first", "Low"),
    ("E08", "COM", "Inverter communication loss",
     "Broken compressor-inverter bus, EMI from unsegregated cabling",
     "Inspect power/control segregation, reseat the inverter harness, verify bus termination resistors", "High"),
    ("E09", "COND", "Condensate tray overflow (float switch)",
     "Blocked condensate drain, unit tilted, failed float switch",
     "Flush condensate tray and drain line (Section 3.3), verify unit level within 2 degrees, test float switch operation", "Medium"),
    ("E10", "GFC", "Earth leakage current detected",
     "Insulation degradation in compressor or pump windings, water ingress at junction box",
     "ISOLATE SUPPLY. Perform insulation resistance test (minimum 1 megohm at 500 V DC). Do not reset repeatedly; follow Chapter 5 electrical safety", "Critical"),
    ("E11", "FAN", "Outdoor fan locked rotor",
     "Seized fan bearings, foreign object, failed motor capacitor or inverter stage",
     "With supply isolated, clear obstruction and rotate fan by hand; measure winding resistance; replace motor if seized", "Medium"),
    ("E12", "RVS", "Reversing valve position error",
     "Reversing valve stuck mid-travel, low differential pressure, faulty solenoid coil",
     "Verify solenoid coil resistance 1.2 kilohm ±10%; exercise valve via service mode 3; replace valve if it stays stuck", "High"),
    ("E41", "DHW", "Domestic hot water tank sensor fault",
     "Disconnected or damaged NTC sensor",
     "As E06; sensor is located on the tank lower third", "Low"),
    ("E63", "PFC", "Inverter PFC stage fault",
     "DC bus undervoltage, weak supply phase, PFC board failure",
     "Check supply impedance; verify DC bus voltage 310-370 V DC; replace PFC board if bus is healthy", "Critical"),
    ("E88", "CFG", "Configuration memory checksum error",
     "Controller parameters corrupted after a power event",
     "Reload the parameter set with the service tool, verify parameters P01-P05, re-commission per Chapter 8", "Low"),
]

X200_SPECS: list[tuple[str, str]] = [
    ("Heating capacity (A7/W35)", "4.0 - 16.0 kW, modulating"),
    ("COP (A7/W35, EN 14825 average)", "4.8"),
    ("Refrigerant", "R32 (A2L), factory charge 1.35 kg"),
    ("Compressor", "Inverter-driven scroll, 30-120 r/s"),
    ("Hydronic connection", "G3/4 external thread, 1.0 - 2.0 bar static"),
    ("Electrical supply", "230 V / 1 ph / 50 Hz, MCA 19.6 A, max breaker 25 A type C"),
    ("Sound power level", "58 dB(A) at full modulation"),
    ("Operating envelope (heating)", "Outdoor -25 °C to +35 °C; water 20 - 65 °C"),
    ("Dimensions / weight", "1 342 x 542 x 818 mm / 96 kg"),
]

X200_WIRING: list[tuple[str, str, str, str]] = [
    # circuit, conductor, terminal, torque
    ("Mains supply (L/N/PE)", "3 x 2.5 mm² H07VN-K or equivalent", "X1: L, N, PE", "1.7 Nm"),
    ("Circulator pump", "3 x 1.5 mm² + PE", "X2: L, N, PE", "0.8 Nm"),
    ("Outdoor fan (EC)", "4 x 1.5 mm² screened", "X3: U, V, W, PE", "0.8 Nm"),
    ("Room controller (bus)", "2 x 0.8 mm² twisted shielded", "X5: A, B", "0.5 Nm"),
    ("NTC sensors (supply/return)", "2 x 0.5 mm² each", "X4: S1/S2", "0.4 Nm"),
    ("Immersion heater backup", "3 x 2.5 mm² + PE", "X6: L1, N, PE", "1.7 Nm"),
]

X200_NTC: list[tuple[str, str]] = [
    ("-10 °C", "55.3 kΩ"),
    ("0 °C", "32.6 kΩ"),
    ("10 °C", "19.9 kΩ"),
    ("25 °C", "10.0 kΩ"),
    ("50 °C", "3.6 kΩ"),
    ("65 °C", "2.2 kΩ"),
]

X200_PARTS: list[tuple[str, str, str, str]] = [
    ("ATX-CMP-0142", "Inverter scroll compressor 16 kW", "1", "Match inverter firmware >= 2.4"),
    ("ATX-FAN-0211", "Outdoor EC fan motor 900 mm", "1", "Includes hub and blades"),
    ("ATX-EEV-0308", "Electronic expansion valve, 480 step", "1", "Re-run auto-tune after replacement"),
    ("ATX-SNS-0405", "NTC sensor kit 10 kΩ (5 sensors)", "1", "Covers supply/return/DHW/outdoor/suction"),
    ("ATX-FLT-0501", "Hydronic G4 filter cartridge", "1", "Replace at every annual service"),
    ("ATX-HX-0602", "Brazed plate heat exchanger 16 kW", "1", "Order with gasket set ATX-GSK-0603"),
    ("ATX-RVS-0701", "4-way reversing valve, 220 V coil", "1", "Nitrogen purge required while brazing"),
    ("ATX-PCB-0800", "Main controller board", "1", "Includes parameter backup battery"),
]

# ------------------------------------------------------------------ V9 data ---

V9_FAULT_ROWS: list[tuple[str, str, str, str, str, str]] = [
    ("E20", "LPEV", "Low evaporator pressure alarm",
     "Low glycol flow, blocked strainer, EEV under-feeding, low R513A charge",
     "Verify glycol flow at least 2.1 m³/h per circuit, clean suction strainer, check EEV step count, verify charge by subcooling", "High"),
    ("E21", "HPCN", "High condenser pressure trip",
     "Condenser fouling, condenser fan stall, hot air recirculation, overcharge",
     "Clean condenser coil, verify fan operation, maintain 1.5 m clearance, verify charge by subcooling", "High"),
    ("E22", "OVL", "Compressor motor overload trip",
     "Process load above rating, liquid floodback from low superheat, voltage imbalance above 2%",
     "Check process load in kW, verify superheat 6-8 K, measure voltage imbalance between phases, inspect motor windings", "High"),
    ("E23", "LGL", "Low glycol level in buffer tank",
     "Loop leak, evaporation over years, failed make-up valve",
     "Top up with 25% propylene glycol mix only (see Chapter 5), leak-test the loop, verify make-up valve seating", "Medium"),
    ("E24", "CAV", "Pump cavitation (acoustic sensor plus differential pressure)",
     "Blocked suction strainer, insufficient NPSH, air in loop, worn impeller",
     "Clean suction strainer, verify tank level above minimum mark, de-aerate the loop, inspect impeller for erosion", "Medium"),
    ("E25", "WDG", "Controller watchdog reset",
     "Firmware fault, control brown-out, EMI on the 24 V control bus",
     "Check 24 V supply stability, reseat control bus terminations, update firmware if recurrent", "Low"),
    ("E26", "FAN", "Condenser EC fan stall (speed feedback lost)",
     "Fan bearing failure, EC driver fault, debris strike",
     "With supply isolated, rotate fan and feel for roughness; read the EC driver error log; replace fan module", "Medium"),
    ("E27", "EEV", "Expansion valve driver fault",
     "EEV stepper wiring open or short, driver board failure",
     "Measure stepper coil resistance 46 Ω ±5% per phase at connector X9; replace driver board if coils are healthy", "High"),
    ("E28", "DTEMP", "Compressor discharge temperature high (above 105 °C)",
     "Low charge, superheat too high, condenser underperformance, compression ratio outside envelope",
     "Verify subcooling and superheat, check EEV feeding, inspect condenser airflow; stop the unit if above 115 °C", "Critical"),
    ("E29", "PHASE", "Phase loss or reverse rotation",
     "Loose supply terminal, contactor pitting, utility phase swap after grid work",
     "ISOLATE SUPPLY. Torque-check supply terminals per the wiring table, verify phase sequence L1-L2-L3, test contactor contacts", "Critical"),
    ("E30", "LSH", "Low superheat alarm (below 3 K) - floodback risk",
     "EEV over-feeding, misplaced suction temperature sensor, charge overfill",
     "Verify suction sensor position in the flow, reduce EEV opening via parameter C07, verify charge weight", "High"),
    ("E31", "HSH", "High superheat alarm (above 15 K)",
     "EEV under-feeding, low charge, distributor or screen restriction",
     "Follow the E28 diagnostic path; check the distributor screen for debris", "Medium"),
    ("E95", "MEM", "NVRAM fault - configuration lost",
     "NVRAM wear beyond 10 years, corruption after power event",
     "Restore configuration from backup file; replace the controller board if recurrent", "Low"),
]

V9_SPECS: list[tuple[str, str]] = [
    ("Cooling capacity (W7/G25)", "20 - 140 kW, twin circuit"),
    ("EER (EN 14511, W30/G15)", "3.1"),
    ("Refrigerant", "R513A (A1), 2 x 4.9 kg factory charge"),
    ("Compressors", "2 x inverter twin-scroll"),
    ("Glycol loop", "25% propylene glycol, flow 2.1 - 14.5 m³/h"),
    ("Electrical supply", "400 V / 3 ph / 50 Hz, 62 A, phase sequence L1-L2-L3 required"),
    ("Sound power level", "72 dB(A) at 100% fans"),
    ("Operating envelope", "Ambient -20 °C to +46 °C; leaving glycol -8 °C to +20 °C"),
    ("Dimensions / weight", "2 200 x 1 100 x 2 150 mm / 640 kg"),
]

V9_WIRING: list[tuple[str, str, str, str]] = [
    ("Mains supply", "4 x 16 mm² flexible", "X1: L1, L2, L3, N + PE bar", "4.5 Nm"),
    ("Circulation pump P01", "4 x 2.5 mm²", "X2: L1, L2, L3, PE", "1.2 Nm"),
    ("Condenser fans (EC bus)", "3 x 1.5 mm² screened", "X3: 24 V, GND, PWM, FB", "0.5 Nm"),
    ("BMS integration (Modbus RTU)", "2 x 0.8 mm² twisted shielded, 120 Ω termination", "X5: A, B", "0.5 Nm"),
    ("Flow switch FS01", "2 x 0.75 mm²", "X6: 11, 14", "0.4 Nm"),
    ("Glycol level sensor", "2 x 0.75 mm²", "X7: +, -", "0.4 Nm"),
]

V9_PARTS: list[tuple[str, str, str, str]] = [
    ("VYC-CMP-2100", "Inverter twin-scroll compressor pair", "1 set", "Replace as matched pair only"),
    ("VYC-PMP-2201", "Circulation pump P01, 1.5 kW", "1", "Includes VYC-SEA-2202 seal kit"),
    ("VYC-SEA-2202", "Pump mechanical seal kit", "1", "Glycol-rated EPDM seals"),
    ("VYC-EEV-2304", "Electronic expansion valve, dual port", "2", "One per refrigerant circuit"),
    ("VYC-SNS-2409", "Pressure/temperature sensor set", "1", "Calibrated 0-30 bar"),
    ("VYC-FLT-2510", "Suction strainer mesh 40", "2", "Clean quarterly, replace annually"),
    ("VYC-FAN-2603", "EC axial condenser fan, 630 mm", "4", "Driver firmware matched"),
    ("VYC-GKY-2700", "Propylene glycol 25% premix, 20 L", "as needed", "Never mix inhibitor brands"),
]

X200_NTC_MD = "\n".join(f"| {t} | {r} |" for t, r in X200_NTC)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join([" --- " for _ in headers]) + "|"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([head, sep, body])


def _fault_table(rows: list[tuple[str, str, str, str, str, str]]) -> str:
    body = _md_table(
        ["Code", "Display", "Symptom", "Likely cause", "Corrective action", "Severity"],
        [list(r) for r in rows],
    )
    return f"Table: Fault code summary\n\n{body}"


def _detail(code: str, title: str, body: str) -> str:
    return f"### {code} {title}\n\n{body.strip()}\n"


# ------------------------------------------------------------------ chapters ---

def x200_overview() -> str:
    return f"""# AriaTherm X200 Heat Pump — Service Manual Overview

This chapter introduces the AriaTherm X200 air-to-water heat pump and explains how
the rest of the manual is organised. The X200 is a monobloc, inverter-driven heat
pump using R32 refrigerant (safety class A2L, mildly flammable) with a hydronic
output for radiator, underfloor, and domestic hot water applications.

## Unit identification

The model plate is located on the right-hand side panel of the outdoor unit. It
lists the model number (X200-04 to X200-16), the serial number (format
`ATX200-XXXX`), refrigerant charge, rated current, and the manufacturing date.
Photograph the nameplate during the first visit to a site; the field app can
read it automatically. Never quote a serial from memory when ordering service
parts.

## Technical specifications

Table: X200 technical specifications (nominal, EN 14511)

| Parameter | Value |
| --- | --- |
{chr(10).join(f"| {k} | {v} |" for k, v in X200_SPECS)}

## Manual conventions

- **DANGER** marks a hazard that will cause death or serious injury if ignored.
- **WARNING** marks a hazard that can cause death or serious injury.
- **CAUTION** marks a hazard that can cause minor injury or property damage.
- Fault codes E01-E88 are described in the Fault Codes chapter; codes are also
  printed on the controller display as three characters (for example `ICE` for E04).
- Chapters 4-6 (wiring, refrigerant safety, maintenance) are safety-relevant:
  work described there must only be performed by certified refrigeration
  personnel with valid F-gas handling certification.

## Related documents

Wiring diagrams ship inside the control-box lid and as a PDF on the service USB
stick. The commissioning checklist is in the Installation chapter.
"""


def x200_fault_codes() -> str:
    details = (
        _detail("E01", "Low suction pressure — diagnostic path", """
**Symptom narrative.** The controller reports E01 / `LOW PRES` and the compressor
stops after a 30-second minimum run. Typically reported in heating season when
the indoor air filter is heavily loaded, or after a poor installation that
under-charged the circuit.

1. Confirm the alarm with the service tool: note suction pressure, superheat,
   and evaporating temperature at the moment of the trip.
2. Inspect the indoor air filter and evaporator coil. A filter with visible
   loading reduces airflow enough to drop suction below 1.8 bar at nominal load.
3. Measure superheat at the compressor suction service valve. Target 5-8 K.
4. If superheat is above 10 K with a clean coil, suspect the electronic
   expansion valve: run service mode 5 and listen for stepper movement.
5. If charge is confirmed low, recover the remaining charge, repair the leak,
   pressure-test with dry nitrogen at 32 bar, evacuate to 250 microns, and
   weigh in 1.35 kg ±20 g of R32. Refrigerant work must follow Chapter 5.
""") + "\n" +
        _detail("E03", "Compressor overcurrent — diagnostic path", """
**Symptom narrative.** E03 / `OVC` usually appears together with high discharge
pressure (E02) or on sites with weak supply. The compressor draws above the
nameplate RLA of 14.2 A and the inverter derates then trips.

1. Read the trip current from the event log (service tool, menu LOG > E03).
2. Measure supply voltage at terminal X1 under load: must stay within
   207-253 V. A supply sagging below 207 V under compressor start is a
   site electrical problem, not a unit fault.
3. Compare running current to RLA at stable operation. Current above RLA at
   normal pressure ratios indicates mechanical wear — plan compressor
   replacement (part ATX-CMP-0142).
4. If current is high only at high discharge pressure, treat as E02 first.
""") + "\n" +
        _detail("E04", "Evaporator coil frost / icing — diagnostic path", """
**Symptom narrative.** The user reports the heat pump "icing up" or losing
heating capacity. The controller detects a suspiciously low evaporating
temperature relative to the air temperature and raises E04 / `ICE` before the
coil blocks solid.

⚠ WARNING: Never chip or scrape ice off the coil. Fins deform and refrigerant
circuits can be punctured. Isolate the outdoor fan supply before clearing
melted water from the drain pan.

1. Check the air filter: the most common cause is a blocked filter reducing
   airflow across the indoor coil.
2. Verify the indoor fan runs at rated speed in service mode 2 (target
   1 150 ±50 rpm at full demand).
3. Check subcooling: below 3 K indicates undercharge; follow the E01 path.
4. Confirm the defrost strategy parameter P14 matches the installed climate
   kit. A mis-set P14 causes nuisance icing at 2-7 °C with high humidity.
5. After correcting the cause, force one defrost cycle via service mode 4 and
   confirm the coil clears within 12 minutes.
""") + "\n" +
        _detail("E10", "Earth leakage — safety-critical response", """
DANGER: Earth leakage means live parts may be exposed to touch through water or
damaged insulation. An E10 / `GFC` alarm must never be reset repeatedly to
"clear" it. Each reset with an active fault risks electric shock and fire.

1. Isolate the supply at the mains isolator and apply lock-out/tag-out.
2. Perform an insulation resistance test at 500 V DC on the compressor and
   pump windings. Minimum acceptable reading is 1 megohm.
3. Inspect the junction box for water ingress; check the cable gland seals.
4. If the compressor fails the test, replace it — do not run the unit on an
   isolation device that only "hides" the leakage.
5. Re-energise only after a passed test and record the readings in the
   service log.
""") + "\n"
    )
    return f"""# AriaTherm X200 — Fault Codes

All X200 protective functions raise a fault code with a four-letter display
alias. Codes marked Critical latch the controller and require a service-tool
reset after the root cause is fixed; Medium codes allow three automatic
restarts before latching; Low codes are advisory.

{_fault_table(X200_FAULT_ROWS)}

## Severity and restart behaviour

- **Critical** (E10, E63): unit locks out immediately. Never bypass.
- **High** (E01, E02, E03, E05, E08, E12): three restarts allowed within one
  hour, then lockout.
- **Medium** (E04, E09, E11): ten restarts allowed within 24 hours.
- **Low** (E06, E07, E41, E88): advisory; affected function degrades.

## Detailed diagnostics for high-impact codes

{details}
## Clearing latched faults

Latched faults clear only from the service tool (menu FAULT > RESET) after the
diagnostic path above has been completed. The tool records the reset with the
technician ID — a legal requirement in several markets for Critical codes.
"""


def x200_maintenance() -> str:
    return """# AriaTherm X200 — Preventive Maintenance

Maintenance intervals assume normal urban air quality. Halve intervals for sites
near coastal salt spray or heavy road traffic. Record all work in the unit log;
the warranty requires it.

## Maintenance schedule

Table: X200 maintenance schedule

| Interval | Item |
| --- | --- |
| Monthly | Indoor air filter check |
| Quarterly | Coil cleaning, condensate tray flush |
| Annually | Refrigerant circuit check, electrical inspection, glycol/water quality |
| Every 5 years | Pressure relief valve replacement |

## 3.1 Monthly — indoor filter check

1. Isolate the indoor fan via the controller service menu (fan stop).
2. Open the filter access panel and slide out the filter cassette.
3. If loading is visible, vacuum the intake face; wash only if the media is
   intact, and dry fully before refitting.
4. Refit the cassette, reset the filter timer (parameter P22), close the panel.
5. Verify static pressure drop is below 60 Pa at nominal airflow.

## 3.2 Quarterly — coil cleaning

1. Isolate electrical supply and apply lock-out/tag-out per Chapter 5.
2. Remove the top fan guard and cover the fan motor with waterproof sheeting.
3. Rinse the outdoor coil top-down with a low-pressure water jet (maximum
   25 bar). Never use a pressure lance closer than 300 mm to the fins.
4. Apply coil cleaner for greasy urban fouling; observe the manufacturer's
   contact time, then rinse.
5. Comb bent fins with a fin comb; more than 10% blocked fin area requires
   professional recoiling.
6. Refit the fan guard, remove lock-out/tag-out, and verify fan current draw
   is below 0.9 A at full speed.

## 3.3 Quarterly — condensate tray flush

1. Isolate the unit and open the drain pan access.
2. Flush the tray and drain line with warm water; add condensate tablets for
   biofilm control.
3. Pour 0.5 L of water into the tray and confirm free flow at the drain end.
4. Manually lift the float switch: the controller must raise E09 within
   10 seconds. If it does not, replace the float switch.
5. Dry the tray and refit the access cover.

## 3.4 Annually — refrigerant circuit and electrical inspection

DANGER: This procedure involves live electrical measurement and refrigerant
circuit access. Certified personnel only. Follow Chapter 5 for lock-out/tag-out
and refrigerant handling.

1. With the unit running, record suction and discharge pressures, superheat,
   subcooling, compressor current, and supply voltage. Compare to commissioning
   values: deviation beyond ±15% requires investigation.
2. Subcooling at nominal load must be 6-9 K. Below 3 K indicates undercharge.
3. Leak-check every flare, braze joint, and service valve with a calibrated
   detector (sensitivity 3 g/yr or better).
4. With supply isolated and locked off, torque-check the terminals listed in
   the wiring chapter (Table: X200 power wiring) to their rated torque.
5. Perform insulation resistance tests on compressor and pump windings
   (minimum 1 megohm at 500 V DC).
6. Inspect contactor contacts; replace at visible pitting over 30% of surface.
7. Verify the pressure relief device date code; replace every 5 years.
8. Update the unit log with all readings.
"""


def x200_wiring() -> str:
    return f"""# AriaTherm X200 — Electrical Wiring

All wiring work requires a qualified electrician. Torque values below are
mandatory — a loose supply terminal is the leading cause of E10 earth-leakage
false alarms and thermal damage at X1.

⚠ WARNING: Isolate the supply and apply lock-out/tag-out before removing the
control-box lid. Verify absence of voltage at X1 with a proven two-pole tester.

## Power wiring

Table: X200 power wiring — conductors and terminal torque

| Circuit | Conductor | Terminal | Torque |
| --- | --- | --- | --- |
{chr(10).join(f"| {c} | {t} | {term} | {tq} |" for c, t, term, tq in X200_WIRING)}

The supply circuit must include a 25 A type C breaker and a 30 mA 30 ms RCD
per local code. Provide 20 mm of slack inside the control box so strain
relief carries the cable weight, not the terminal.

## Control wiring

Sensors are 10 kΩ NTC type, two-wire, unscreened up to 5 m. Route sensor cables
at least 100 mm from power cables; EMI from the inverter harness otherwise
produces sensor noise that shows up as hunting water temperature.

The Modbus RTU bus (room controller, energy meter) uses terminals X5 A/B,
twisted shielded pair, shield earthed at one end only, 120 Ω termination at
both physical ends of the bus.

![X200 field wiring diagram](figures/x200_field_wiring.png)

Figure: Field wiring overview — power left, sensors and bus right. The inverter
harness (thick grey) must keep its 100 mm separation from sensor wiring.

## Sensor resistance reference

Table: X200 NTC sensor resistance (10 kΩ type)

| Temperature | Resistance |
| --- | --- |
{X200_NTC_MD}

A sensor reading more than ±5% from the table at a measured temperature is
out of tolerance. Replace with kit ATX-SNS-0405; never splice sensor cables
inside the refrigerant envelope.
"""


def x200_safety() -> str:
    return """# AriaTherm X200 — Refrigerant Handling Safety (R32, A2L)

SAFETY-CRITICAL CHAPTER. This chapter is a precondition for any work that opens
the refrigerant circuit. R32 is classified A2L: lower flammability, but still
flammable. The procedures below are minimum requirements; local F-gas
regulations always take precedence.

DANGER: Never braze, weld, or grind on any part of the refrigerant circuit
while it contains refrigerant. Decomposition products from burning R32 include
hydrogen fluoride, which is lethal at low concentration and causes permanent
lung damage.

## Work permit and ventilation

1. Before opening the circuit, complete the refrigerant work permit: unit ID,
   charge weight, task, technician certification number.
2. Work in a ventilated area: keep the room volume rule of at least 20 m³ of
   free air per kilogram of R32 in the circuit. The X200 carries 1.35 kg, so
   work outdoors or with forced ventilation at floor level (R32 is heavier
   than air and pools).
3. Use A2L-rated recovery equipment and cylinders only. Standard R410A
   cylinders and gauges are not rated for R32 service pressure.
4. Ban ignition sources within 3 m: no smoking, no non-ATEX power tools, no
   brazing until the circuit is verified empty and nitrogen-purged.

## Recovery procedure

1. Connect the recovery machine and A2L-rated recovery cylinder; weigh the
   cylinder before and after (recovered mass must match nameplate ±10%).
2. Recover to below 0.5 bar residual pressure.
3. Break the vacuum with dry nitrogen to 0.5 bar and re-recover. This sweep
   removes residual refrigerant from oil pockets.
4. Only now may brazing equipment be lit. Keep the nitrogen flowing.

## Brazing with nitrogen purge

DANGER: Brazing without a nitrogen purge produces copper oxide scale that
blocks the expansion valve and contaminates the compressor oil. Brazing on a
charged circuit is prohibited without exception.

1. Flow dry nitrogen at 1-2 L/min, circuit pressure 0.2-0.5 bar, from the
   far end of the section being brazed toward the joint.
2. Braze with a oxygen-acetylene or oxy-hydrogen torch; move continuously,
   never dwell on one spot. Wrap wet heat-sink cloth around valves and the
   plate heat exchanger.
3. Let joints cool under nitrogen flow until below 150 °C.

## Pressure test and evacuation

1. Pressure-test the repaired section with dry nitrogen at 32 bar (PS test
   pressure) held for 30 minutes. Temperature change moves the reading about
   0.1 bar per °C — correct for it before declaring a pass.
2. Evacuate to 250 microns with the vacuum decay test: rise must stay below
   50 microns in 10 minutes with the pump isolated.
3. Weigh in R32 as a liquid, 1.35 kg ±20 g, or per the repair record if the
   circuit was partially emptied.

## Leak checking

Use a heated-diode or infrared detector calibrated to 3 g/yr sensitivity.
Check every flare (re-torque per the table below after the first season),
every braze, and both service valves. A detector alarm at any joint requires
the joint to be remade, not "topped up".

Table: X200 flare joint torque values

| Tube size | Torque |
| --- | --- |
| 1/4 inch | 10-12 Nm |
| 3/8 inch | 18-21 Nm |
| 1/2 inch | 28-34 Nm |
| 5/8 inch | 38-45 Nm |

## A2L cylinder handling

Store cylinders upright, chained, out of sunlight below 45 °C. Transport
secured upright with the valve cap fitted. Never refill a disposable cylinder.
Full and empty cylinders are segregated and labelled; a cylinder whose content
is unknown is treated as full until proven otherwise.
"""


def x200_troubleshooting() -> str:
    return """# AriaTherm X200 — Troubleshooting Guides

Decision trees for the most common field reports. Each tree ends at a fault
code, a maintenance procedure, or a safety chapter reference. Work top-down;
do not skip branches.

## 6.1 No heating at all

1. Is the display powered?
   - No: check breaker and isolator, then 230 V at X1. If power is present and
     the display is dark, replace the controller (ATX-PCB-0800).
   - Yes: continue.
2. Is there an active fault code?
   - Yes: look up the code in the Fault Codes chapter and follow its path.
   - No: continue.
3. Is a heating demand present (controller shows request)?
   - No: check the room controller wiring at X5 and the Modbus bus.
   - Yes: continue.
4. Is the compressor running (listen at the outdoor unit)?
   - No: check E08 inverter communication and the DC bus (E63 path).
   - Yes: continue.
5. Is water flow present (pump running, flow switch made)?
   - No: follow E05.
   - Yes: measure flow and return temperatures; if both rise equally the unit
     is heating — the fault is in the emitter circuit, not the heat pump.

## 6.2 Reduced heating capacity / icing complaints

1. Clean or replace the air filter, then re-test (Section 3.1).
2. Inspect the outdoor coil for fouling or icing; follow the E04 path.
3. Record superheat and subcooling:
   - Subcooling below 3 K: undercharge — follow E01 and Chapter 5 recovery.
   - Superheat above 10 K: expansion valve — run service mode 5.
4. Verify water flow rate is 0.36-0.58 m³/h per 4 kW of demand.
5. If capacity is still low with correct readings, compare current draw to
   commissioning data; a compressor losing displacement shows as high current
   with low delta-T — plan replacement.

## 6.3 Breaker trips repeatedly

1. Note which breaker: main, pump, or backup heater.
2. Main breaker: measure compressor running current vs RLA and insulation
   resistance — follow the E03 and E10 paths.
3. Backup heater breaker: check the immersion element for water ingress
   (insulation test) and the contactor for welding.
4. Repeated trips with no measurable cause indicate a weak supply: verify
   impedance at X1 and involve the site electrician.

## 6.4 Water around the indoor unit

1. Confirm the water is condensate, not a hydraulic leak: condensate is
   intermittent and correlates with defrosts.
2. Condensate: flush tray and drain line (Section 3.3), verify unit level.
3. Hydraulic leak: isolate the water side, repair the joint, re-pressurise to
   1.0-1.5 bar static, and de-aerate.

## 6.5 Noisy operation

1. Rattle at the outdoor fan: remove debris, check fan blade clearance.
2. Humming with no compressor start: DC bus undervoltage — E63 path.
3. Gurgling in water pipes: air in the hydraulic circuit — de-aerate.
4. Loud transport bolts: check that the compressor transport bolts were
   removed at installation.
"""


def x200_parts() -> str:
    return f"""# AriaTherm X200 — Service Parts

Order with the unit serial number (format ATX200-XXXX). Parts marked with a
refrigerant-circuit note may only be fitted by certified personnel following
the refrigerant handling chapter.

Table: X200 service parts list (BOM extract)

| Part number | Description | Qty | Notes |
| --- | --- | --- | --- |
{chr(10).join(f"| {p} | {d} | {q} | {n} |" for p, d, q, n in X200_PARTS)}

## Ordering rules

1. Quote serial, not model: mid-production revisions changed the expansion
   valve and the controller board.
2. Compressor and controller ship as freight-only; do not courier.
3. Sensor kit ATX-SNS-0405 covers every NTC in the unit; individual sensors
   are not supplied separately.
4. Returns require the original packaging; refrigerant-circuit parts returned
   opened are not credited.

![X200 exploded view, hydraulic module](figures/x200_exploded_hydraulic.png)

Figure: Exploded view of the hydraulic module. Callouts match the part numbers
in the table above.
"""


def x200_installation() -> str:
    return """# AriaTherm X200 — Installation and Commissioning

## Siting

Table: X200 minimum clearances

| Direction | Clearance |
| --- | --- |
| Air outlet (top) | 2 500 mm |
| Air intake sides | 300 mm |
| Service access front | 600 mm |
| Wall (rear) | 50 mm |

Do not site the unit where defrost water can freeze across walkways. Maintain
at least 3 m from bedroom windows: full-modulation sound power is 58 dB(A).

## Hydraulic connection

1. Fit isolating valves and a Y-strainer (500 µm) on the return line.
2. Connect the flow and return to G3/4 fittings; support pipe weight off the
   unit connections.
3. Fill the circuit with inhibitor-treated water to 1.0-1.5 bar static.
4. Flush until the return water runs clear; the warranty voids on sludge.
5. De-aerate via the auto-vent and the pump bleed screw.
6. Verify flow switch operation by closing a valve: E05 must raise within
   15 seconds.

## Commissioning checklist

1. Torque-check all electrical terminals (wiring chapter table).
2. Verify RCD trip function with the test button.
3. Set parameters P01-P05 per the commissioning sheet:
   - P01 heat curve midpoint, P02 curve slope, P03 DHW target,
   - P04 hysteresis, P05 pump speed.
4. Run heating mode: record flow/return temperatures, compressor current,
   pressures, superheat, and subcooling after 20 minutes of stable running.
5. Force one defrost (service mode 4) and time it: 8-12 minutes nominal.
6. Test the backup heater contactor and interlock.
7. Hand over: register the warranty with the serial, hand the log book to the
   owner, and photograph the nameplate for the site record.
"""


def v9_overview() -> str:
    return f"""# VeyraCool V9 Chiller — Service Manual Overview

The VeyraCool V9 is an air-cooled glycol chiller with two independent
refrigerant circuits (R513A, safety class A1 non-flammable), inverter
twin-scroll compressors, and EC condenser fans. Typical duty: process cooling
and comfort chilled water 20-140 kW.

## Unit identification

The nameplate is inside the electrical cabinet door and duplicated on the
frame end panel. Model codes run V9-020 to V9-140 (nominal kW). The serial
format is `VYC9-XXXX`. Both refrigerant circuits have separate nameplate
charge weights — quote circuit A and B charges separately when ordering
refrigerant.

## Technical specifications

Table: V9 technical specifications (nominal, EN 14511)

| Parameter | Value |
| --- | --- |
{chr(10).join(f"| {k} | {v} |" for k, v in V9_SPECS)}

## Safety orientation

- The unit contains pressurised circuits up to 28.5 bar test pressure and
  rotating machinery with automatic restart. Lock-out/tag-out is mandatory
  before any panel is opened.
- R513A is A1 (non-flammable) but displaces oxygen: never work inside the
  unit enclosure in a basement plant room without verifying ventilation.
- The glycol loop is treated with inhibitor; spillages are slippery and must
  be contained. Never mix glycol brands.

## Manual layout

Fault codes (E20-E95) are in the Fault Codes chapter. Safety — refrigerant and
electrical — is consolidated in the Safety chapter, which takes precedence
over any procedure described elsewhere.
"""


def v9_fault_codes() -> str:
    details = (
        _detail("E20", "Low evaporator pressure — diagnostic path", """
**Symptom narrative.** Circuit A or B reports E20 / `LPEV`. Common after a
strainer is left dirty through seasonal start-up, or when the glycol loop is
partially closed for maintenance elsewhere in the building.

1. Confirm glycol flow at the flow meter: minimum 2.1 m³/h per circuit at
   nominal load.
2. Check the suction strainer differential pressure sensor: above 0.4 bar
   across the strainer means clean or replace the mesh (VYC-FLT-2510).
3. Verify the evaporator differential pressure and loop valves are fully open.
4. Record superheat. Above 10 K with healthy flow points at EEV under-feeding:
   check EEV step count against demand (driver fault is E27).
5. If subcooling is below 2 K, charge is low: recover, repair, pressure-test,
   evacuate, and weigh in per the Safety chapter. Circuit charge is 4.9 kg.
""") + "\n" +
        _detail("E21", "High condenser pressure — diagnostic path", """
**Symptom narrative.** E21 / `HPCN` on hot days, or after coil fouling through
poplar seed season. The controller trips at 26 bar.

1. Inspect condenser coils externally; wash top-down with a water jet at
   moderate pressure with fans isolated.
2. Check every EC fan reports speed feedback; a stalled fan is E26.
3. Verify free discharge air: 1.5 m clearance and no recirculation walls.
4. If pressures stay high with a clean coil and healthy fans, check for
   overcharge or non-condensables: recover the charge, weigh it, purge and
   re-weigh in. Non-condensables show as high head pressure with normal
   subcooling and a high discharge temperature.
""") + "\n" +
        _detail("E28", "High discharge temperature — safety-critical response", """
WARNING: Discharge temperature above 115 °C breaks down oil and can damage the
compressor within minutes. Do not keep the unit running to "observe" the
fault. Reduce load or stop the unit.

1. Stop or derate the affected circuit immediately.
2. Verify superheat: above 15 K (E31 path) drives discharge temperature up.
3. Check subcooling: below 2 K indicates low charge.
4. Inspect the condenser: fouling or fan loss raises compression ratio.
5. If the fault recurs at correct superheat/subcooling, log the discharge
   temperature trend and contact the factory — a compression ratio outside
   the application envelope requires application review, not parts.
""") + "\n" +
        _detail("E30", "Low superheat — floodback risk", """
WARNING: Sustained superheat below 3 K sends liquid refrigerant back to the
compressor. Floodback washes oil out of the bearings and destroys twin-scroll
compressors quietly and quickly.

1. Verify the suction temperature sensor is fully in the flow at the 6 o'clock
   position of the suction line, within 300 mm of the compressor.
2. Compare EEV step count to the commissioning trend; over-feeding shows as
   high step counts at low load.
3. Reduce EEV opening limit via parameter C07 in 5% steps, rechecking
   superheat after 10 minutes of stable running.
4. Verify charge weight on the next planned outage; overfill mimics an EEV
   fault.
""") + "\n"
    )
    return f"""# VeyraCool V9 — Fault Codes

Codes are per-circuit unless marked unit-level. The display shows the circuit
letter: `A:E28` is circuit A discharge temperature.

{_fault_table(V9_FAULT_ROWS)}

## Severity and restart behaviour

- **Critical** (E28, E29): immediate lockout of the affected circuit, service
  tool reset required.
- **High** (E20, E21, E22, E27, E30): three restarts within one hour, then
  circuit lockout. The other circuit keeps running.
- **Medium** (E23, E24, E26, E31): ten restarts within 24 hours.
- **Low** (E25, E95): advisory; capacity may derate.

## Detailed diagnostics for high-impact codes

{details}
"""


def v9_maintenance() -> str:
    return """# VeyraCool V9 — Preventive Maintenance

## Maintenance schedule

Table: V9 maintenance schedule

| Interval | Item |
| --- | --- |
| Monthly | Glycol level and concentration visual check |
| Quarterly | Suction strainer clean, condenser coil wash |
| Semi-annual | Pump seal inspection, superheat verification |
| Annually | Electrical torque audit, glycol inhibitor analysis, refrigerant leak check |

## 3.1 Monthly — glycol concentration check

1. Draw a sample at the loop drain point into a clean jar; let it reach 20 °C.
2. Measure with a refractometer: target 25% propylene glycol by volume,
   tolerance ±2%. The mix protects to -12 °C.
3. Below 23%: top up with premixed 25% VYC-GKY-2700 only. Never add
   concentrate or water directly to the loop.
4. Record the reading; a falling trend without visible leaks points at the
   make-up valve or evaporation at the buffer tank vent.
5. Annually, send a sample for inhibitor titration; reinhibit if reserve
   alkalinity is below 400 ppm.

## 3.2 Quarterly — suction strainer clean

1. Stop the affected circuit and close its isolating valves; verify zero
   pressure at the strainer gauge before opening.
2. Remove the strainer basket and wash the 40-mesh insert.
3. Inspect for debris: metal particles mean compressor wear — take a sample
   and investigate before restart.
4. Fit a new basket gasket, reassemble, open valves, and de-aerate the pocket.
5. Record the differential pressure after restart: below 0.2 bar clean.

## 3.3 Semi-annual — pump seal inspection

1. Isolate the pump electrically and hydraulically.
2. Inspect the seal face for weeping tracks; light staining is normal, a
   drip every few minutes is not.
3. Replace the seal with kit VYC-SEA-2202 if leakage is visible after wiping:
   glycol attacks standard NBR seals, the kit is EPDM-rated.
4. Verify motor current draw below nameplate after restart.

## 3.4 Semi-annual — superheat verification

1. With the circuit stable at nominal load, read superheat at the controller
   and verify with a probe at the sensor location.
2. Target 6-8 K. Record the value on both circuits.
3. Superheat outside 3-15 K: follow the E30 (low) or E31 (high) paths.
4. Confirm the EEV control is stable: hunting above ±2 K indicates the C07
   opening limit or sensor placement needs review.

## 3.5 Annually — electrical torque audit

WARNING: Live-panel work is prohibited. Isolate, lock off, and verify absence
of voltage before touching any terminal.

1. Torque-check every power terminal to the wiring chapter table; record.
2. Thermographic survey under load before isolation: any terminal more than
   15 °C above its phase partners gets re-torqued and re-surveyed.
3. Inspect contactors for pitting; replace above 30% surface damage.
4. Verify phase sequence L1-L2-L3 after any utility work: reverse rotation on
   scroll compressors is silent and destructive (E29).
"""


def v9_wiring() -> str:
    return f"""# VeyraCool V9 — Electrical Wiring

⚠ WARNING: Isolate the supply, apply lock-out/tag-out, and verify absence of
voltage with a proven tester before opening panel A1. The unit has two
separate supply feeds on some sites (compressor and controls); isolate both.

## Power wiring

Table: V9 power wiring — conductors and terminal torque

| Circuit | Conductor | Terminal | Torque |
| --- | --- | --- | --- |
{chr(10).join(f"| {c} | {t} | {term} | {tq} |" for c, t, term, tq in V9_WIRING)}

The supply requires a 62 A breaker per circuit feed and phase sequence
L1-L2-L3. Scroll compressors rotate backwards silently on a reversed supply;
the phase monitor raises E29 but rotation damage is not reversible — verify
sequence after every utility intervention with a phase sequencer, not by
trial.

## Control wiring and BMS

The Modbus RTU bus (X5 A/B) runs to the BMS head end, twisted shielded pair,
shield earthed at the panel end only, 120 Ω termination at both ends. Maximum
bus length 500 m at 19.2 kbaud. Register map version 3 ships with the unit;
firmware 4.2 changed registers C01-C12.

Flow switch FS01 (terminal X6) is a dry contact rated 250 V / 2 A: it must
break the compressor enable chain directly, not only via software.

![V9 electrical cabinet layout](figures/v9_cabinet_layout.png)

Figure: Cabinet A1 layout. Left: power feeds and contactors. Right: controller,
EC fan bus, and Modbus termination. The 24 V control supply must stay
segregated from 400 V wiring by the marked barrier.
"""


def v9_safety() -> str:
    return """# VeyraCool V9 — Safety: Refrigerant, Pressurised Systems and Electrical

SAFETY-CRITICAL CHAPTER. This chapter consolidates every safety-critical
procedure for the V9. Where any other chapter conflicts with this one, this
chapter wins.

## Refrigerant handling (R513A, A1)

1. R513A is non-flammable but displaces oxygen. In basement plant rooms,
   verify mechanical ventilation is running before opening the circuit.
2. Recovery must use equipment rated for R513A (HFO blends attack some seal
   materials); weigh recovered charge against the circuit nameplate 4.9 kg.
3. After any repair: pressure-test with dry nitrogen at 28.5 bar for 30
   minutes (correct readings for ambient temperature), evacuate to 250
   microns with a decay test below 50 microns in 10 minutes, then weigh in
   charge as liquid.
4. Leak-check annually with a detector calibrated to 3 g/yr; log every joint
   checked. HFO blends fractionate on leakage — never top up a leaking
   circuit; recover, repair, and reweigh.

## Pressurised systems

DANGER: The glycol loop and refrigerant circuits hold stored energy. Never
loosen any fitting on a pressurised system. Verify zero pressure at a gauge
you have yourself seen at zero.

1. Glycol loop: close isolating valves, vent to zero at the drain point, and
   crack fittings slowly with a rag wrap.
2. Refrigerant circuit: recover to below 0.5 bar before opening.
3. Relief valves: verify date codes annually; replace at 5 years. Never
   cap or bypass a relief device, even temporarily.
4. Burst disc on the condenser side vents to the frame vent: keep the vent
   clear and pointed away from walkways.

## Electrical safety and lock-out/tag-out

DANGER: Contact with 400 V terminals is lethal. The unit has capacitor banks
that stay charged after isolation.

1. LOTO sequence: open all supply feeds, apply personal locks, tag with name
   and date, then verify absence of voltage at X1 with a proven two-pole
   tester (prove the tester on a known live source before and after).
2. DC link capacitors: wait at least 10 minutes after isolation, then measure
   the DC bus; work only below 30 V DC.
3. Phase loss work (E29): never "test by swapping" phases with the unit
   energised. Use a phase sequencer on an isolated supply.
4. Live measurement under load (thermographic surveys, current checks) is
   permitted only for qualified personnel with arc-rated PPE per site policy.

## Glycol handling

Propylene glycol is low-hazard but slippery; contain spills immediately with
granules, never with water hoses that spread it. Used glycol is controlled
waste: dispose per local rules, never to storm drains. Keep the safety data
sheet with the service kit.
"""


def v9_troubleshooting() -> str:
    return """# VeyraCool V9 — Troubleshooting Guides

## 6.1 Not cooling / leaving water temperature too high

1. Compare setpoint and actual leaving glycol temperature; confirm the
   control loop is in cooling demand.
2. Check both circuits are running (one circuit down halves capacity).
   A stopped circuit shows its code — follow that code's path.
3. Verify glycol flow: below 2.1 m³/h per circuit raises E20 and starves the
   evaporator — clean the strainer (Section 3.2 of Maintenance).
4. Check the condenser: fouling or fan faults raise head pressure and cut
   capacity — follow E21.
5. Record superheat and subcooling on the running circuit:
   - Superheat above 15 K: E31 path (under-feeding or low charge).
   - Subcooling below 2 K: charge low — Safety chapter recovery procedure.
6. If a process side load was recently increased, verify the application is
   still within the unit curve; capacity falls about 2.5% per °C of ambient
   above 25 °C.

## 6.2 Overload trips (E22)

1. Read the trip current and the process load in kW.
2. Verify superheat: below 3 K means floodback — follow E30 before replacing
   anything.
3. Measure voltage imbalance: above 2% derates the motor — involve the site
   electrician.
4. Insulation test the motor if trips continue at healthy pressures.

## 6.3 Pump cavitation noise (E24)

1. Verify buffer tank level above the minimum mark.
2. Clean the suction strainer.
3. De-aerate the loop at the high points and pump volute.
4. Inspect the impeller for erosion cavities; replace the pump if pitted.

## 6.4 Repeated high pressure trips (E21)

1. Wash the condenser coils (fans isolated).
2. Verify every fan has speed feedback; replace stalled modules.
3. Check discharge air recirculation (walls added after installation are a
   classic cause).
4. If clean with healthy fans: recover and weigh the charge; suspect
   non-condensables after any service without proper evacuation.

## 6.5 Superheat hunting

1. Verify the suction sensor sits fully in the flow near the compressor.
2. Reduce EEV opening limit (C07) in 5% steps and observe for 10 minutes.
3. Check the charge weight against the nameplate.
4. If hunting persists at correct charge and sensor placement, update
   firmware: versions below 4.2 had an EEV control improvement.
"""


def v9_parts() -> str:
    return f"""# VeyraCool V9 — Service Parts

Order with unit serial and circuit letter. Refrigerant-circuit parts require
certified installation per the Safety chapter.

Table: V9 service parts list (BOM extract)

| Part number | Description | Qty | Notes |
| --- | --- | --- | --- |
{chr(10).join(f"| {p} | {d} | {q} | {n} |" for p, d, q, n in V9_PARTS)}

## Ordering rules

1. Quote serial VYC9-XXXX and circuit (A/B) for every refrigerant-side part.
2. Compressors ship as matched pairs; single-scroll orders are rejected.
3. Seal kit VYC-SEA-2202 is EPDM — standard NBR kits fail with glycol.
4. EC fans carry driver firmware; mixing versions on one unit is not
   supported — order all four together if any one fails with firmware
   mismatch.

![V9 hydraulic module exploded view](figures/v9_exploded_hydraulic.png)

Figure: Hydraulic module exploded view with pump, strainer, and buffer tank
callouts matching the parts table.
"""


CHAPTERS: list[tuple[str, str]] = [
    ("ariatherm_x200_00_overview.md", x200_overview()),
    ("ariatherm_x200_01_fault_codes.md", x200_fault_codes()),
    ("ariatherm_x200_02_maintenance.md", x200_maintenance()),
    ("ariatherm_x200_03_wiring.md", x200_wiring()),
    ("ariatherm_x200_04_refrigerant_safety.md", x200_safety()),
    ("ariatherm_x200_05_troubleshooting.md", x200_troubleshooting()),
    ("ariatherm_x200_06_parts.md", x200_parts()),
    ("ariatherm_x200_07_installation.md", x200_installation()),
    ("veyracool_v9_00_overview.md", v9_overview()),
    ("veyracool_v9_01_fault_codes.md", v9_fault_codes()),
    ("veyracool_v9_02_maintenance.md", v9_maintenance()),
    ("veyracool_v9_03_wiring.md", v9_wiring()),
    ("veyracool_v9_04_safety.md", v9_safety()),
    ("veyracool_v9_05_troubleshooting.md", v9_troubleshooting()),
    ("veyracool_v9_06_parts.md", v9_parts()),
]


def build_all() -> list[tuple[str, str]]:
    """Pure function: filename -> markdown content. Deterministic by construction."""
    return list(CHAPTERS)


def write_corpus(out_dir: Path) -> dict[str, str]:
    """Write every chapter; return filename -> sha256 manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for name, content in build_all():
        target = out_dir / name
        target.write_text(content, encoding="utf-8", newline="\n")
        manifest[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic HVAC-Copilot corpus.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "corpus",
        help="output directory (default: repo corpus/)",
    )
    parser.add_argument("--manifest", action="store_true", help="print the sha256 manifest as JSON")
    args = parser.parse_args(argv)
    manifest = write_corpus(args.out)
    print(f"wrote {len(manifest)} chapters to {args.out}")
    if args.manifest:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
