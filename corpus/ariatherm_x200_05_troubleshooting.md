# AriaTherm X200 — Troubleshooting Guides

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
