#!/usr/bin/env bash
# Final test: run SafeHome and evaluate.py on the handwritten reports only.
#
# Fill in handwritten/labels.csv (same columns as data/labels.csv) and handwritten/reports.csv
# (id, text) first. Keep these reports out of prompt work, so this stays a fair final test.
# Usage, from anywhere:  ./evaluation/run_final_test.sh
set -euo pipefail

cd "$(dirname "$0")"
PY="${PYTHON:-python}"
[ -x ../.venv/bin/python ] && PY="${PYTHON:-../.venv/bin/python}"
DIR=handwritten

# Refuse to run on unfinished templates: every label needs an id, hazard and level, every report text.
"$PY" - "$DIR" <<'EOF'
import csv, sys
d = sys.argv[1]
labels = list(csv.DictReader(open(f"{d}/labels.csv", encoding="utf-8")))
reports = list(csv.DictReader(open(f"{d}/reports.csv", encoding="utf-8")))
problems = [f"labels row {n}: needs id, hazard and level" for n, r in enumerate(labels, 2)
            if not (r["id"].strip() and r["hazard"].strip() and r["level"].strip())]
problems += [f"reports row {n}: needs id and text" for n, r in enumerate(reports, 2)
             if not (r["id"].strip() and r["text"].strip())]
missing = {r["id"] for r in labels} - {r["id"] for r in reports}
if missing:
    problems.append(f"no report text for: {', '.join(sorted(missing))}")
if problems:
    sys.exit("Fill in the handwritten files first:\n  " + "\n  ".join(problems[:10]))
EOF

"$PY" run_safehome.py --data "$DIR" --out "$DIR/predictions/safehome.csv" | tee "$DIR/run.log"
if grep -q "via keywords" "$DIR/run.log"; then
  echo "Stopped: some reports were read with keywords, not Claude. Check ANTHROPIC_API_KEY in .env." >&2
  exit 2
fi

"$PY" evaluate.py --labels "$DIR/labels.csv" --results "$DIR/results" "$DIR/predictions/safehome.csv"
