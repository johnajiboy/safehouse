import csv
import subprocess
import sys
from pathlib import Path

EVALUATION = Path(__file__).resolve().parent.parent / "evaluation"


def test_handwritten_templates_match_the_main_labels():
    main = next(csv.reader(open(EVALUATION / "data/labels.csv", encoding="utf-8")))
    rows = list(csv.reader(open(EVALUATION / "handwritten/labels.csv", encoding="utf-8")))
    assert rows[0] == main and len(rows) == 31
    reports = list(csv.reader(open(EVALUATION / "handwritten/reports.csv", encoding="utf-8")))
    assert reports[0] == ["id", "text"] and len(reports) == 31


def test_scripts_run_on_another_folder(tmp_path):
    """The final test reads and writes only its own folder (keyword reader, no API calls)."""
    header = next(csv.reader(open(EVALUATION / "data/labels.csv", encoding="utf-8")))
    with open(tmp_path / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, header)
        w.writeheader()
        w.writerow({**dict.fromkeys(header, ""), "id": "H01", "hazard": "Fire and explosions",
                    "level": "Emergency", "vulnerability": "None", "repeat": "no", "style": "short"})
    with open(tmp_path / "reports.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["id", "text"], ["H01", "Strong smell of gas in the kitchen"]])
    run = lambda *args: subprocess.run([sys.executable, *args], cwd=EVALUATION, check=True,
                                       capture_output=True, text=True).stdout
    run("run_safehome.py", "--keywords", "--data", str(tmp_path), "--out", str(tmp_path / "p.csv"))
    out = run("evaluate.py", "--labels", str(tmp_path / "labels.csv"), "--results", str(tmp_path / "res"),
              str(tmp_path / "p.csv"))
    assert "Emergencies missed" in out and (tmp_path / "res/p.json").exists()
