"""Step 4: score predictions against the answer key.

Your Intake Agent must write a CSV with these columns:
  id, hazard, level, vulnerability, repeat, confidence
  (optional) predicted_cluster  - a group name for reports your Pattern Agent links together

Run:  python evaluate.py predictions/baseline.csv
      python evaluate.py predictions/safehome.csv
      python evaluate.py predictions/baseline.csv predictions/safehome.csv   (side by side)
      python evaluate.py --labels handwritten/labels.csv --results handwritten/results handwritten/predictions/safehome.csv
Output: printed results, plus results/<name>.json
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

URGENCY = {"Emergency": 3, "Significant": 2, "Officer review": 2, "Routine": 1}


def norm(x):
    return (x or "").strip().lower()


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score(pred_path, labels_path="data/labels.csv"):
    labels = {r["id"]: r for r in csv.DictReader(open(labels_path, encoding="utf-8"))}
    preds = {r["id"]: r for r in csv.DictReader(open(pred_path, encoding="utf-8"))}
    ids = [i for i in labels if i in preds]
    missing = [i for i in labels if i not in preds]
    res = {"file": pred_path, "reports_scored": len(ids), "reports_missing": len(missing)}

    # 1. Hazard type: accuracy and per-class precision / recall / F1
    classes = sorted({labels[i]["hazard"] for i in ids})
    per = {}
    for c in classes:
        tp = sum(norm(preds[i]["hazard"]) == norm(c) and labels[i]["hazard"] == c for i in ids)
        fp = sum(norm(preds[i]["hazard"]) == norm(c) and labels[i]["hazard"] != c for i in ids)
        fn = sum(norm(preds[i]["hazard"]) != norm(c) and labels[i]["hazard"] == c for i in ids)
        p, r, f = prf(tp, fp, fn)
        per[c] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "count": tp + fn}
    res["hazard_accuracy"] = round(sum(norm(preds[i]["hazard"]) == norm(labels[i]["hazard"]) for i in ids) / len(ids), 3)
    res["hazard_macro_f1"] = round(sum(v["f1"] for v in per.values()) / len(per), 3)
    res["hazard_per_class"] = per

    # 2. Safety: emergencies missed is the most important number
    emerg = [i for i in ids if labels[i]["level"] == "Emergency"]
    missed = [i for i in emerg if norm(preds[i]["level"]) != "emergency"]
    over = [i for i in ids if labels[i]["level"] != "Emergency" and norm(preds[i]["level"]) == "emergency"]
    res["emergencies_total"] = len(emerg)
    res["emergencies_missed"] = len(missed)
    res["emergencies_missed_ids"] = missed
    res["emergency_recall"] = round(1 - len(missed) / len(emerg), 3) if emerg else None
    res["false_emergencies"] = len(over)
    under = [i for i in ids if URGENCY.get(preds[i]["level"].strip(), 0) < URGENCY[labels[i]["level"]]]
    res["under_prioritised"] = len(under)  # any report ranked less urgent than it should be
    res["level_accuracy"] = round(sum(norm(preds[i]["level"]) == norm(labels[i]["level"]) for i in ids) / len(ids), 3)

    # 3. Household vulnerability and repeat reports
    vtp = sum(labels[i]["vulnerability"] != "None" and norm(preds[i]["vulnerability"]) == norm(labels[i]["vulnerability"]) for i in ids)
    vfp = sum(norm(preds[i]["vulnerability"]) not in ("", "none") and norm(preds[i]["vulnerability"]) != norm(labels[i]["vulnerability"]) for i in ids)
    vfn = sum(labels[i]["vulnerability"] != "None" and norm(preds[i]["vulnerability"]) != norm(labels[i]["vulnerability"]) for i in ids)
    p, r, f = prf(vtp, vfp, vfn)
    res["vulnerability"] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}
    rtp = sum(labels[i]["repeat"] == "yes" and norm(preds[i]["repeat"]) == "yes" for i in ids)
    rfp = sum(labels[i]["repeat"] == "no" and norm(preds[i]["repeat"]) == "yes" for i in ids)
    rfn = sum(labels[i]["repeat"] == "yes" and norm(preds[i]["repeat"]) != "yes" for i in ids)
    p, r, f = prf(rtp, rfp, rfn)
    res["repeat"] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}

    # 4. Fairness: the same problem in different styles should get the same hazard and level
    groups = defaultdict(list)
    for i in ids:
        if labels[i]["group_id"]:
            groups[labels[i]["group_id"]].append(i)
    unfair = [g for g, m in groups.items()
              if len({(norm(preds[i]["hazard"]), norm(preds[i]["level"])) for i in m}) > 1]
    res["fairness_groups"] = len(groups)
    res["fairness_consistent"] = round(1 - len(unfair) / len(groups), 3) if groups else None
    res["fairness_inconsistent_groups"] = unfair
    by_style = defaultdict(list)
    for i in ids:
        by_style[labels[i]["style"]].append(norm(preds[i]["hazard"]) == norm(labels[i]["hazard"]))
    res["hazard_accuracy_by_style"] = {s: round(sum(v) / len(v), 3) for s, v in sorted(by_style.items())}

    # 5. Confidence: are mistakes flagged for an officer?
    wrong = [i for i in ids if norm(preds[i]["hazard"]) != norm(labels[i]["hazard"])
             or norm(preds[i]["level"]) != norm(labels[i]["level"])]
    flagged = [i for i in wrong if norm(preds[i].get("confidence")) == "low"]
    res["mistakes"] = len(wrong)
    res["mistakes_flagged_low_confidence"] = len(flagged)
    unclear = [i for i in ids if labels[i]["hazard"] == "Unclear"]
    res["unclear_sent_to_officer"] = sum(norm(preds[i]["level"]) == "officer review"
                                         or norm(preds[i].get("confidence")) == "low" for i in unclear)
    res["unclear_total"] = len(unclear)

    # 6. Pattern detection (only if a predicted_cluster column exists): pairwise precision / recall
    if ids and "predicted_cluster" in preds[ids[0]]:
        pairs = list(combinations(ids, 2))
        same_true = {(a, b) for a, b in pairs if labels[a]["cluster_id"] and labels[a]["cluster_id"] == labels[b]["cluster_id"]}
        same_pred = {(a, b) for a, b in pairs if preds[a]["predicted_cluster"] and preds[a]["predicted_cluster"] == preds[b]["predicted_cluster"]}
        p, r, f = prf(len(same_true & same_pred), len(same_pred - same_true), len(same_true - same_pred))
        res["pattern_pairs"] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}

    # Confusion pairs, to see what gets mixed up
    res["top_confusions"] = Counter(f"{labels[i]['hazard']} -> {preds[i]['hazard']}" for i in ids
                                    if norm(preds[i]["hazard"]) != norm(labels[i]["hazard"])).most_common(5)
    return res


def show(results):
    names = [Path(r["file"]).stem for r in results]
    rows = [
        ("Reports scored", "reports_scored"),
        ("Hazard accuracy", "hazard_accuracy"),
        ("Hazard macro F1", "hazard_macro_f1"),
        ("Level accuracy", "level_accuracy"),
        ("Emergencies missed (lower is better)", "emergencies_missed"),
        ("Emergency recall", "emergency_recall"),
        ("False emergencies", "false_emergencies"),
        ("Under-prioritised reports", "under_prioritised"),
        ("Vulnerability F1", ("vulnerability", "f1")),
        ("Repeat report F1", ("repeat", "f1")),
        ("Fairness groups consistent", "fairness_consistent"),
        ("Mistakes flagged low confidence", None),
        ("Unclear reports sent to officer", None),
        ("Pattern pairs F1", ("pattern_pairs", "f1")),
    ]
    w = max(len(n) for n in names) + 4
    print(f"\n{'Measure':40}" + "".join(f"{n:>{w}}" for n in names))
    print("-" * (40 + w * len(names)))
    for label, key in rows:
        vals = []
        for r in results:
            if key is None and label.startswith("Mistakes"):
                v = f"{r['mistakes_flagged_low_confidence']}/{r['mistakes']}"
            elif key is None:
                v = f"{r['unclear_sent_to_officer']}/{r['unclear_total']}"
            elif isinstance(key, tuple):
                v = r.get(key[0], {}).get(key[1], "-")
            else:
                v = r.get(key, "-")
            vals.append(str(v))
        print(f"{label:40}" + "".join(f"{v:>{w}}" for v in vals))
    for r, n in zip(results, names):
        print(f"\n{n}: hazard accuracy by writing style {r['hazard_accuracy_by_style']}")
        if r["emergencies_missed_ids"]:
            print(f"{n}: missed emergencies {r['emergencies_missed_ids']}")
        if r["fairness_inconsistent_groups"]:
            print(f"{n}: inconsistent fairness groups {r['fairness_inconsistent_groups']}")
        if r["top_confusions"]:
            print(f"{n}: most common mix-ups {r['top_confusions']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", nargs="+", help="prediction CSV files to score side by side")
    parser.add_argument("--labels", default="data/labels.csv", help="the answer key")
    parser.add_argument("--results", default="results", help="folder for the JSON results")
    args = parser.parse_args()
    out = [score(p, args.labels) for p in args.predictions]
    results = Path(args.results)
    results.mkdir(parents=True, exist_ok=True)
    for r in out:
        (results / f"{Path(r['file']).stem}.json").write_text(json.dumps(r, indent=2))
    show(out)
    print(f"\nFull results saved in {results}/")
