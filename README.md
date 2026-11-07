# SafeHome

An intelligent decision support system that helps social housing officers prioritise tenant hazard reports, meet Awaab's Law deadlines and book suitable repairers. An officer makes every final decision.

## How it works

1. **Intake Agent** (`safehome/intake.py`) reads a tenant's report with the Claude API and records the hazard, household needs and repeat reports, quoting the exact words used as evidence. Without an API key it falls back to keyword matching.
2. **Legal rules** (`safehome/rules.py`) set the level (emergency, significant, routine or officer review) and the Awaab's Law deadlines. Rules can raise a level but never lower one.
3. **Planner** (`safehome/planner.py`) ranks cases by severity, deadline, vulnerability and time reported, then fits them to the inspectors on shift.
4. **Pattern Agent** (`safehome/patterns.py`) links damp and cold reports from the same building that may share a cause.
5. **Repair Agent** (`safehome/repairs.py`) shortlists approved repairers by trade, availability, distance and first-time fix rate.
6. **Messages** (`safehome/messages.py`): emergencies get fixed safety advice at once. Every other message waits for officer approval.
7. **Decision log** (`safehome/store.py`) records every agent action and officer decision.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your Anthropic API key to .env
```

## Run

```bash
python -m safehome.seed            # load the sample reports
python -m safehome.auth add <name> # create an officer account (asks for a password)
uvicorn safehome.api:app --reload
```

Open http://localhost:8000 for the intro, http://localhost:8000/report.html for the tenant form, or
http://localhost:8000/dashboard.html for the officer dashboard (you'll be asked to sign in).

## Test

```bash
pytest                             # unit tests, no API calls
python -m safehome.simulation      # planner compared with simpler methods
```

## Evaluate report reading

```bash
cd evaluation
python make_labels.py              # answer key (already included in data/labels.csv)
python generate_reports.py         # tenant messages written with Claude
python baseline_keywords.py        # simple keyword method to compare against
python run_safehome.py             # SafeHome's predictions
python evaluate.py predictions/baseline.csv predictions/safehome.csv
```

Check the labels as a group before generating reports, and keep about 30 reports aside as a final test you don't use while improving prompts.

## Notes

- Map positions are approximate area locations, not tenants' homes. Map data © OpenStreetMap contributors.
- Repairers and sample reports are invented. Middlesbrough area names are real.
- Bank holidays are not counted in working-day deadlines yet.
- Text messages and emails are recorded in the database only. Connecting a real messaging service is future work.
- The SQLite database suits a single-machine demo. A shared deployment would need a hosted database.
