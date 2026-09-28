# AriaTherm X200 — Fault Codes

All X200 protective functions raise a fault code with a four-letter display
alias. Codes marked Critical latch the controller and require a service-tool
reset after the root cause is fixed; Medium codes allow three automatic
restarts before latching; Low codes are advisory.

Table: Fault code summary

| Code | Display | Symptom | Likely cause | Corrective action | Severity |
| --- | --- | --- | --- | --- | --- |
| E01 | LOW PRES | Low suction pressure alarm; compressor cycles off | Refrigerant undercharge, evaporator airflow restriction, or expansion valve stuck closed | Verify airflow (filter/indoor coil), check superheat at service ports; if charge is low, recover and weigh in per Chapter 5 | High |
| E02 | HIGH PRES | High discharge pressure trip | Condenser fouling, outdoor fan failure, non-condensables in circuit, overcharge | Clean condenser coil, verify outdoor fan operation, check for non-condensables, verify charge by subcooling | High |
| E03 | OVC | Compressor overcurrent trip | High discharge pressure, supply voltage out of range, failing compressor bearings | Measure running current against nameplate RLA; check supply voltage within ±10%; inspect compressor if current is high at normal pressures | High |
| E04 | ICE | Evaporator coil iced; reduced heating capacity | Low airflow (dirty filter, failed indoor fan) or low refrigerant charge | Inspect and clean filter and indoor coil; verify fan runs at rated speed; check subcooling per Chapter 6 Section 5.4 | Medium |
| E05 | FLOW | No or low hydronic water flow | Closed isolating valve, blocked Y-strainer, failed circulator pump, airlock | Check valve positions, clean Y-strainer, bleed the hydraulic circuit, measure pump differential pressure | High |
| E06 | SNT | Supply water sensor fault (open/short circuit) | Disconnected or damaged NTC sensor, faulty harness | Measure sensor resistance against the NTC table in Chapter 4; replace sensor if outside tolerance | Low |
| E07 | SNR | Return water sensor fault (open/short circuit) | Disconnected or damaged NTC sensor, faulty harness | As E06; verify connector seating at terminal X4 first | Low |
| E08 | COM | Inverter communication loss | Broken compressor-inverter bus, EMI from unsegregated cabling | Inspect power/control segregation, reseat the inverter harness, verify bus termination resistors | High |
| E09 | COND | Condensate tray overflow (float switch) | Blocked condensate drain, unit tilted, failed float switch | Flush condensate tray and drain line (Section 3.3), verify unit level within 2 degrees, test float switch operation | Medium |
| E10 | GFC | Earth leakage current detected | Insulation degradation in compressor or pump windings, water ingress at junction box | ISOLATE SUPPLY. Perform insulation resistance test (minimum 1 megohm at 500 V DC). Do not reset repeatedly; follow Chapter 5 electrical safety | Critical |
| E11 | FAN | Outdoor fan locked rotor | Seized fan bearings, foreign object, failed motor capacitor or inverter stage | With supply isolated, clear obstruction and rotate fan by hand; measure winding resistance; replace motor if seized | Medium |
| E12 | RVS | Reversing valve position error | Reversing valve stuck mid-travel, low differential pressure, faulty solenoid coil | Verify solenoid coil resistance 1.2 kilohm ±10%; exercise valve via service mode 3; replace valve if it stays stuck | High |
| E41 | DHW | Domestic hot water tank sensor fault | Disconnected or damaged NTC sensor | As E06; sensor is located on the tank lower third | Low |
| E63 | PFC | Inverter PFC stage fault | DC bus undervoltage, weak supply phase, PFC board failure | Check supply impedance; verify DC bus voltage 310-370 V DC; replace PFC board if bus is healthy | Critical |
| E88 | CFG | Configuration memory checksum error | Controller parameters corrupted after a power event | Reload the parameter set with the service tool, verify parameters P01-P05, re-commission per Chapter 8 | Low |

## Severity and restart behaviour

- **Critical** (E10, E63): unit locks out immediately. Never bypass.
- **High** (E01, E02, E03, E05, E08, E12): three restarts allowed within one
  hour, then lockout.
- **Medium** (E04, E09, E11): ten restarts allowed within 24 hours.
- **Low** (E06, E07, E41, E88): advisory; affected function degrades.

## Detailed diagnostics for high-impact codes

### E01 Low suction pressure — diagnostic path

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

### E03 Compressor overcurrent — diagnostic path

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

### E04 Evaporator coil frost / icing — diagnostic path

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

### E10 Earth leakage — safety-critical response

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


## Clearing latched faults

Latched faults clear only from the service tool (menu FAULT > RESET) after the
diagnostic path above has been completed. The tool records the reset with the
technician ID — a legal requirement in several markets for Critical codes.
