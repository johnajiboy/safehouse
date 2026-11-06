"""Run SafeHome's Intake Agent and rules over the test reports.

Run from the evaluation folder:
    python run_safehome.py              (uses Claude if ANTHROPIC_API_KEY is set)
    python run_safehome.py --keywords   (keyword reader only, no API calls)
Output: predictions/safehome.csv, ready for evaluate.py
"""
import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safehome import intake, patterns, rules  # noqa: E402
from safehome.models import Case  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", action="store_true", help="use the keyword reader instead of Claude")
    args = parser.parse_args()

    labels = {row["id"]: row for row in csv.DictReader(open("data/labels.csv", encoding="utf-8"))}
    reports = list(csv.DictReader(open("data/reports.csv", encoding="utf-8")))
    now = datetime.now()

    cases = []
    for number, report in enumerate(reports, 1):
        started = time.time()
        reader = intake.extract_with_keywords if args.keywords else intake.extract
        extraction = reader(report["text"])
        decision = rules.decide_level(extraction, report["text"])
        label = labels[report["id"]]
        cases.append(Case(
            ref=report["id"], text=report["text"], address=label["address"], area=label["area"],
            reported_at=now, extraction=extraction, level=decision.level, level_reasons=decision.reasons,
        ))
        print(f"{number}/{len(reports)} {report['id']} {extraction.hazard} ({decision.level}) "
              f"via {extraction.source} in {time.time() - started:.1f}s")

    cluster_of = {}
    for cluster in patterns.find_clusters(cases, now):
        for ref in cluster.refs:
            cluster_of[ref] = cluster.key

    Path("predictions").mkdir(exist_ok=True)
    with open("predictions/safehome.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "hazard", "level", "vulnerability", "repeat", "confidence", "predicted_cluster"])
        for case in cases:
            ex = case.extraction
            writer.writerow([
                case.ref, ex.hazard, case.level,
                ex.vulnerability[0] if ex.vulnerability else "None",
                "yes" if ex.repeat else "no",
                ex.hazard_confidence,
                cluster_of.get(case.ref, ""),
            ])
    print("Saved predictions/safehome.csv")


if __name__ == "__main__":
    main()
