# Summary fact-checking study: baseline (no AI) condition

Participants judge whether an AI-written summary is **Faithful** or **Hallucinated**
with respect to a source passage (FaithBench, curated in `hw2/`). This is the
human-only baseline; the AI-assisted condition will reuse the same app with
`study.CONDITION = "ai"`.

## Flow (~8 min)

1. **Instructions** (time logged): the task, the passage-only rule, and two worked
   examples (one Faithful, one Hallucinated with the bad phrase highlighted). Both
   examples summarize the same passage, which is removed from the sampling pool.
2. **Rule quiz** (attention check 1): two questions on the rule. Wrong answers show
   the rule again and allow a retry; every attempt is logged.
3. **7 trials**, one per screen, forward-only, with the passage and summary side by side:
   - 6 real trials, randomly sampled per participant: 3 Hallucinated + 3 Faithful,
     each from a different source passage.
   - 1 hand-written catch trial (attention check 2) at a random position, never first.
   - For each trial: answer (Faithful / Hallucinated), confidence (50-100), and
     seconds on the trial (logged automatically).
4. **End screen** with an access code; the start page can look up a past session.

**Termination rule (tolerant):** the session ends only if the participant fails the
catch trial **and** needed 3+ quiz attempts. Failing just one check sets
`attention_flag` but lets them finish. Terminated sessions are saved too.

## Measurements

| Measure | Why it matters |
|---|---|
| Accuracy (vs. FaithBench gold) | Primary task performance; comparable with AI-alone accuracy (63.4%). |
| Time per trial | Efficiency. AI help only pays off if it saves time or improves accuracy at similar time cost. |
| Confidence per trial (50-100) | Same scale as the AI's confidence, so human calibration (e.g. ECE, confidence on correct vs. wrong answers) can be compared with the AI's (ECE 0.358) and across conditions, e.g. whether AI help makes people overconfident. |
| Instruction reading time, quiz attempts, catch result | Data quality / exclusion criteria. |

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit interface |
| `study.py` | Constants, examples, catch trial, quiz, sampling, and termination rule |
| `storage.py` | Firestore storage (collection `baseline_sessions`, one doc per participant) |
| `export_csv.py` | Export all sessions to `baseline_responses.csv`, one row per trial |
| `check_sampling.py` | Simulates 5000 participants and checks label balance, unique passages, and example exclusion |
| `study_dataset.csv` | Copy of `hw2/study_dataset.csv` (304 trials) |

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # paste Firebase key
.venv/bin/streamlit run app.py
```

Without a `[firestore]` section in secrets, the app runs in dev mode and writes to
`.local_sessions.json` (`python export_csv.py --local` exports it).

## Deploy (Streamlit Community Cloud)

Push this folder to a GitHub repo (the `.gitignore` keeps `secrets.toml` out), create
an app pointing at `app.py`, and paste the contents of `.streamlit/secrets.toml` into
the app's **Secrets** setting.
