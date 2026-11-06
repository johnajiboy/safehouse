# Label changes

Changes made to `data/labels.csv` by hand after the reports were generated. Running
`make_labels.py` again rebuilds `labels.csv` from scratch and would undo them.

## Emergency definition

A report is an emergency when it describes any of:

- a gas smell
- sparks from electrics
- exposed or bare wiring
- a collapsed ceiling, or a structure about to fall
- a hole someone could fall through
- a total loss of heating in cold weather

Small pieces of falling plaster, cracks, or a missing smoke alarm on their own are Significant.

## 2026-11-06: five reports raised from Significant to Emergency

The labels came from short facts, but the generated report text describes a risk that meets the
emergency definition above.

| ID | Hazard | Was | Now | Reason |
|---|---|---|---|---|
| T058 | Structural collapse | Significant | Emergency | Garden wall "looks like it could come down at any point": a structure about to fall |
| T059 | Structural collapse | Significant | Emergency | Garden wall "looks like it could fall at any moment": a structure about to fall |
| T065 | Fire and explosions | Significant | Emergency | Smoke alarm gone, leaving "just a bare wire": bare wiring |
| T067 | Fire and explosions | Significant | Emergency | Smoke alarm missing, "bare wires sticking out": bare wiring |
| T068 | Fire and explosions | Significant | Emergency | Smoke alarm missing, "only the wires and a small hole": bare wiring |

## 2026-11-06: two more reports raised from Significant to Emergency

Both come from the same leaning-wall facts as T058 and T059. They describe the same risk in a
calmer tone, and tone shouldn't change the label.

| ID | Hazard | Was | Now | Reason |
|---|---|---|---|---|
| T057 | Structural collapse | Significant | Emergency | Garden wall "appears to be at risk of falling": same as T058/T059 |
| T060 | Structural collapse | Significant | Emergency | Garden wall "looks like it could come down": same as T058/T059 |
