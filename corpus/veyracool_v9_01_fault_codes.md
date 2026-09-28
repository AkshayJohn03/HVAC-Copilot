# VeyraCool V9 — Fault Codes

Codes are per-circuit unless marked unit-level. The display shows the circuit
letter: `A:E28` is circuit A discharge temperature.

Table: Fault code summary

| Code | Display | Symptom | Likely cause | Corrective action | Severity |
| --- | --- | --- | --- | --- | --- |
| E20 | LPEV | Low evaporator pressure alarm | Low glycol flow, blocked strainer, EEV under-feeding, low R513A charge | Verify glycol flow at least 2.1 m³/h per circuit, clean suction strainer, check EEV step count, verify charge by subcooling | High |
| E21 | HPCN | High condenser pressure trip | Condenser fouling, condenser fan stall, hot air recirculation, overcharge | Clean condenser coil, verify fan operation, maintain 1.5 m clearance, verify charge by subcooling | High |
| E22 | OVL | Compressor motor overload trip | Process load above rating, liquid floodback from low superheat, voltage imbalance above 2% | Check process load in kW, verify superheat 6-8 K, measure voltage imbalance between phases, inspect motor windings | High |
| E23 | LGL | Low glycol level in buffer tank | Loop leak, evaporation over years, failed make-up valve | Top up with 25% propylene glycol mix only (see Chapter 5), leak-test the loop, verify make-up valve seating | Medium |
| E24 | CAV | Pump cavitation (acoustic sensor plus differential pressure) | Blocked suction strainer, insufficient NPSH, air in loop, worn impeller | Clean suction strainer, verify tank level above minimum mark, de-aerate the loop, inspect impeller for erosion | Medium |
| E25 | WDG | Controller watchdog reset | Firmware fault, control brown-out, EMI on the 24 V control bus | Check 24 V supply stability, reseat control bus terminations, update firmware if recurrent | Low |
| E26 | FAN | Condenser EC fan stall (speed feedback lost) | Fan bearing failure, EC driver fault, debris strike | With supply isolated, rotate fan and feel for roughness; read the EC driver error log; replace fan module | Medium |
| E27 | EEV | Expansion valve driver fault | EEV stepper wiring open or short, driver board failure | Measure stepper coil resistance 46 Ω ±5% per phase at connector X9; replace driver board if coils are healthy | High |
| E28 | DTEMP | Compressor discharge temperature high (above 105 °C) | Low charge, superheat too high, condenser underperformance, compression ratio outside envelope | Verify subcooling and superheat, check EEV feeding, inspect condenser airflow; stop the unit if above 115 °C | Critical |
| E29 | PHASE | Phase loss or reverse rotation | Loose supply terminal, contactor pitting, utility phase swap after grid work | ISOLATE SUPPLY. Torque-check supply terminals per the wiring table, verify phase sequence L1-L2-L3, test contactor contacts | Critical |
| E30 | LSH | Low superheat alarm (below 3 K) - floodback risk | EEV over-feeding, misplaced suction temperature sensor, charge overfill | Verify suction sensor position in the flow, reduce EEV opening via parameter C07, verify charge weight | High |
| E31 | HSH | High superheat alarm (above 15 K) | EEV under-feeding, low charge, distributor or screen restriction | Follow the E28 diagnostic path; check the distributor screen for debris | Medium |
| E95 | MEM | NVRAM fault - configuration lost | NVRAM wear beyond 10 years, corruption after power event | Restore configuration from backup file; replace the controller board if recurrent | Low |

## Severity and restart behaviour

- **Critical** (E28, E29): immediate lockout of the affected circuit, service
  tool reset required.
- **High** (E20, E21, E22, E27, E30): three restarts within one hour, then
  circuit lockout. The other circuit keeps running.
- **Medium** (E23, E24, E26, E31): ten restarts within 24 hours.
- **Low** (E25, E95): advisory; capacity may derate.

## Detailed diagnostics for high-impact codes

### E20 Low evaporator pressure — diagnostic path

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

### E21 High condenser pressure — diagnostic path

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

### E28 High discharge temperature — safety-critical response

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

### E30 Low superheat — floodback risk

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


