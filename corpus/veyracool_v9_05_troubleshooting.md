# VeyraCool V9 — Troubleshooting Guides

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
