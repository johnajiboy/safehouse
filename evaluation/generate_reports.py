"""Step 2: write a realistic tenant message for every label, using the Claude API.

The model only sees the facts and the writing style, never the hazard category
name or level, so the messages read like real tenants and don't give away the answer.

Run:   python generate_reports.py            (needs ANTHROPIC_API_KEY)
Test:  python generate_reports.py --dry-run  (no API key, writes placeholder text)
Output: data/reports.csv  (id, text)

It skips reports that are already written, so you can stop and restart it safely.
"""
import argparse
import csv
import os
import time
from pathlib import Path

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

VULN_HINT = {
    "None": "Do not mention anyone vulnerable living there.",
    "Young child": "Mention naturally that a baby or young child lives there.",
    "Older person": "Mention naturally that an older relative lives there (give an age over 75 or say elderly).",
    "Pregnancy": "Mention naturally that the tenant is pregnant.",
    "Mobility need": "Mention naturally that someone uses a wheelchair or walking frame.",
    "Long-term health condition": "Mention naturally that someone has a breathing problem made worse by the home.",
}
STYLE_HINT = {
    "formal": "polite and formal, like an email",
    "casual": "casual, like a quick text message",
    "simple English": "simple English from someone still learning the language, with small grammar mistakes",
    "angry": "frustrated and angry, but not abusive",
    "short": "very short, one or two sentences, but still include every fact",
}

PROMPT = """Write one message from a social housing tenant in Middlesbrough to their landlord's repairs team.

Facts to include: {facts}.
{vuln}
{repeat}
Writing style: {style}.
Their address is {address}, {area}. Mention it only if it feels natural.

Rules:
- Describe what they see, hear or smell. Never use official hazard category names.
- Do not invent extra problems or people.
- 1 to 4 sentences. Use no real person's name.
- Reply with the message only, no quotation marks."""

UNCLEAR_PROMPT = """Write one short, vague message from a social housing tenant in Middlesbrough to their landlord.
The tenant says that {facts}, but gives no clear detail about any danger.
Writing style: {style}. 1 to 3 sentences. Reply with the message only."""


def build_prompt(r):
    if r["hazard"] == "Unclear":
        return UNCLEAR_PROMPT.format(facts=r["facts"], style=STYLE_HINT[r["style"]])
    return PROMPT.format(
        facts=r["facts"],
        vuln=VULN_HINT[r["vulnerability"]],
        repeat="Say they have reported this before and it still isn't fixed." if r["repeat"] == "yes"
        else "Do not say it has been reported before.",
        style=STYLE_HINT[r["style"]],
        address=r["address"], area=r["area"],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="write placeholder text without calling the API")
    args = ap.parse_args()

    labels = list(csv.DictReader(open("data/labels.csv", encoding="utf-8")))
    out = Path("data/reports.csv")
    done = {}
    if out.exists():
        done = {r["id"]: r["text"] for r in csv.DictReader(open(out, encoding="utf-8"))}

    client = None
    if not args.dry_run:
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic()

    for i, r in enumerate(labels, 1):
        if r["id"] in done:
            continue
        if args.dry_run:
            text = f"[{r['style']}] {r['facts']}." + (" My baby lives here." if r["vulnerability"] == "Young child" else "")
        else:
            for attempt in range(5):
                try:
                    msg = client.messages.create(model=MODEL, max_tokens=300, temperature=1,
                                                 messages=[{"role": "user", "content": build_prompt(r)}])
                    text = msg.content[0].text.strip().strip('"')
                    break
                except Exception as e:  # rate limits or network errors: wait and retry
                    wait = 2 ** attempt
                    print(f"  {r['id']} failed ({e.__class__.__name__}), retrying in {wait}s")
                    time.sleep(wait)
            else:
                print(f"  {r['id']} skipped after 5 tries")
                continue
        done[r["id"]] = text
        # save after every report so nothing is lost if it stops
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "text"])
            w.writerows([[k, done[k]] for k in sorted(done)])
        print(f"{i}/{len(labels)} {r['id']}: {text[:70]}")

    print(f"Done. {len(done)} reports in {out}")


if __name__ == "__main__":
    main()
