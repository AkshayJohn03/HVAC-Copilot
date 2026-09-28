# AriaTherm X200 — Electrical Wiring

All wiring work requires a qualified electrician. Torque values below are
mandatory — a loose supply terminal is the leading cause of E10 earth-leakage
false alarms and thermal damage at X1.

⚠ WARNING: Isolate the supply and apply lock-out/tag-out before removing the
control-box lid. Verify absence of voltage at X1 with a proven two-pole tester.

## Power wiring

Table: X200 power wiring — conductors and terminal torque

| Circuit | Conductor | Terminal | Torque |
| --- | --- | --- | --- |
| Mains supply (L/N/PE) | 3 x 2.5 mm² H07VN-K or equivalent | X1: L, N, PE | 1.7 Nm |
| Circulator pump | 3 x 1.5 mm² + PE | X2: L, N, PE | 0.8 Nm |
| Outdoor fan (EC) | 4 x 1.5 mm² screened | X3: U, V, W, PE | 0.8 Nm |
| Room controller (bus) | 2 x 0.8 mm² twisted shielded | X5: A, B | 0.5 Nm |
| NTC sensors (supply/return) | 2 x 0.5 mm² each | X4: S1/S2 | 0.4 Nm |
| Immersion heater backup | 3 x 2.5 mm² + PE | X6: L1, N, PE | 1.7 Nm |

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
| -10 °C | 55.3 kΩ |
| 0 °C | 32.6 kΩ |
| 10 °C | 19.9 kΩ |
| 25 °C | 10.0 kΩ |
| 50 °C | 3.6 kΩ |
| 65 °C | 2.2 kΩ |

A sensor reading more than ±5% from the table at a measured temperature is
out of tolerance. Replace with kit ATX-SNS-0405; never splice sensor cables
inside the refrigerant envelope.
