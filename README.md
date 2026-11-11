# Summary fact-checking study

Participants judge whether an AI-written summary is **Faithful** or **Hallucinated**
with respect to a source passage (FaithBench, curated in `hw2/`). Two conditions
are deployed from this repo as separate Streamlit apps:

| Condition | Entry file | Firestore collection |
|---|---|---|
| Baseline (no AI) | `app.py` | `baseline_sessions` |
| AI-assisted | `app_ai.py` | `ai_sessions` |

Both use the same sampling, rule quiz, catch trial, and termination rule (`study.py`).

---

## Baseline condition

### Flow (~8 min)

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

### Measurements

| Measure | Why it matters |
|---|---|
| Accuracy (vs. FaithBench gold) | Primary task performance; comparable with AI-alone accuracy (63.4%). |
| Time per trial | Efficiency. AI help only pays off if it saves time or improves accuracy at similar time cost. |
| Confidence per trial (50-100) | Same scale as the AI's confidence, so human calibration (e.g. ECE, confidence on correct vs. wrong answers) can be compared with the AI's (ECE 0.358) and across conditions, e.g. whether AI help makes people overconfident. |
| Instruction reading time, quiz attempts, catch result | Data quality / exclusion criteria. |

## AI-assisted condition (`app_ai.py`)

Asynchronous AI assistance: the saved Assignment 2 outputs of Gemini 3.5 Flash-Lite
(`study_dataset_with_predictions.csv`, rows identical to `study_dataset.csv`).

- **Instructions** add an "About the AI assistant" section that states the AI is
  correct on about 6 of 10 summaries and misses many hallucinations. The two worked
  examples show the AI's real output: correct on A, and a miss on B.
- **Two-stage trials:** (1) the participant answers alone (answer + confidence); (2)
  the AI's verdict appears in a card under the summary and, if the verdict is
  Hallucinated, its flagged phrase is highlighted in blue inside the summary. The
  final answer and confidence are pre-filled with the initial ones and can be changed.
  The AI's confidence (100 on 84% of trials) and rationale are not shown.
- **Catch trial** is scored on the stage-1 answer, before the AI is shown, so simply
  agreeing with the AI can't pass it.
- **Post-study survey** (1-7 agreement): trust in the AI, helpfulness of the
  highlights, and self-reported reliance.
- **Logged per trial:** initial and final answer, confidence, and time; AI verdict,
  span, and correctness; `switched`, `agree_initial`, `agree_final`,
  `over_reliance` (switched to a wrong AI), and `under_reliance` (kept an answer
  that disagreed with a correct AI). `answer`/`correct`/`confidence` hold the final
  answer and `seconds` the total for both stages, so columns line up with the baseline.

## Files

| File | Purpose |
|---|---|
| `app.py` | Baseline Streamlit interface |
| `app_ai.py` | AI-assisted Streamlit interface |
| `study.py` | Constants, examples, catch trial, quiz, sampling, and termination rule |
| `storage.py` | Firestore storage, one doc per participant (collection chosen per condition) |
| `export_csv.py` | Export sessions to `<condition>_responses.csv`, one row per trial (`--condition ai` for the AI condition) |
| `check_sampling.py` | Simulates 5000 participants and checks label balance, unique passages, and example exclusion |
| `study_dataset.csv` | Copy of `hw2/study_dataset.csv` (304 trials) |
| `study_dataset_with_predictions.csv` | Copy of the same file from `hw2/`, with the saved AI outputs |

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # paste Firebase key
.venv/bin/streamlit run app.py      # or app_ai.py
```

Without a `[firestore]` section in secrets, the apps run in dev mode and write to
`.local_sessions.json` / `.local_ai_sessions.json` (`python export_csv.py --local
[--condition ai]` exports them).

## Deploy (Streamlit Community Cloud)

Push this folder to a GitHub repo (the `.gitignore` keeps `secrets.toml` out). Create
one app per condition from the same repo and branch, with **Main file path** `app.py`
or `app_ai.py`, and paste the contents of `.streamlit/secrets.toml` into each app's
**Secrets** setting (secrets are per app).
