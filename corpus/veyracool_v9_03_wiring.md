# VeyraCool V9 — Electrical Wiring

⚠ WARNING: Isolate the supply, apply lock-out/tag-out, and verify absence of
voltage with a proven tester before opening panel A1. The unit has two
separate supply feeds on some sites (compressor and controls); isolate both.

## Power wiring

Table: V9 power wiring — conductors and terminal torque

| Circuit | Conductor | Terminal | Torque |
| --- | --- | --- | --- |
| Mains supply | 4 x 16 mm² flexible | X1: L1, L2, L3, N + PE bar | 4.5 Nm |
| Circulation pump P01 | 4 x 2.5 mm² | X2: L1, L2, L3, PE | 1.2 Nm |
| Condenser fans (EC bus) | 3 x 1.5 mm² screened | X3: 24 V, GND, PWM, FB | 0.5 Nm |
| BMS integration (Modbus RTU) | 2 x 0.8 mm² twisted shielded, 120 Ω termination | X5: A, B | 0.5 Nm |
| Flow switch FS01 | 2 x 0.75 mm² | X6: 11, 14 | 0.4 Nm |
| Glycol level sensor | 2 x 0.75 mm² | X7: +, - | 0.4 Nm |

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
