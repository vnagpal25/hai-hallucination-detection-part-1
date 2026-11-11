"""Study design: constants, trial sampling, and attention-check rules.

Kept free of Streamlit so the sampling logic can be checked from a plain script
(see check_sampling.py).
"""

import random
import secrets

import pandas as pd

CONDITION = "baseline"  # the AI-assisted condition will set this to "ai"

DATASET_PATH = "study_dataset.csv"
N_PER_LABEL = 3  # 3 Hallucinated + 3 Faithful real trials
N_REAL = 2 * N_PER_LABEL
N_TOTAL = N_REAL + 1  # plus one catch trial

FAITHFUL = "Faithful"
HALLUCINATED = "Hallucinated"
LABELS = [FAITHFUL, HALLUCINATED]
CONFIDENCE_LEVELS = [50, 60, 70, 80, 90, 100]

# Worked examples in the instructions. Both summarize the same short passage, so
# that passage is removed from the sampling pool entirely (every row that uses it).
EXAMPLE_FAITHFUL_ID = 220
EXAMPLE_HALLUCINATED_ID = 88
EXAMPLE_HALLUCINATED_SPAN = "and it is featured on"
EXAMPLE_HALLUCINATED_REASON = (
    "The passage describes two different things that share the name "
    '"Hourglass": a song by Disclosure and an album by James Taylor. It never says '
    "the song appears on the album, so the summary invents a connection."
)

# Hand-written attention check, shown at a random position among the real trials.
# The summary contradicts the passage on two concrete facts.
CATCH_TRIAL = {
    "trial_id": -1,
    "source": (
        "The Maple Street Bakery opened in 2012 in Portland, Oregon. "
        "It is open every day except Monday and is best known for its blueberry muffins."
    ),
    "summary": (
        "The Maple Street Bakery opened in 2012 in Portland, Oregon. It is open every "
        "day of the week and is best known for its chocolate croissants."
    ),
    "label": HALLUCINATED,
}

# Rule quiz shown after the instructions. A wrong answer re-shows the rule and
# the participant retries; attempts are logged.
QUIZ = [
    {
        "key": "q_real_world",
        "question": (
            "A summary includes a fact that is true in the real world, but the passage "
            "never mentions it. How should you label the summary?"
        ),
        "answer": HALLUCINATED,
    },
    {
        "key": "q_paraphrase",
        "question": (
            "A summary uses different words than the passage, but every claim it makes "
            "is supported by the passage. How should you label the summary?"
        ),
        "answer": FAITHFUL,
    },
]

# Terminate only when both checks look careless: the catch trial is answered
# wrong AND the quiz took more than one retry (3+ attempts).
MAX_QUIZ_ATTEMPTS_TOLERATED = 2

# access codes are typed by hand, so leave out characters that look alike (1, I, 0, O)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def new_code():
    """Random participant ID, also handed out as the access code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def load_dataset(path=DATASET_PATH):
    return pd.read_csv(path)


def sampling_pool(df):
    """All rows except those that share a passage with the worked examples."""
    example_sources = set(
        df.loc[df.trial_id.isin([EXAMPLE_FAITHFUL_ID, EXAMPLE_HALLUCINATED_ID]), "source"]
    )
    return df[~df.source.isin(example_sources)]


def sample_trials(df, rng=None):
    """Pick N_PER_LABEL rows of each label, each from a different source passage,
    then insert the catch trial at a random position other than the first.

    Returns a list of dicts with keys trial_id, source, summary, label, is_catch.
    """
    rng = rng or random.Random()
    pool = sampling_pool(df)
    order = list(pool.index)
    rng.shuffle(order)

    picked, used_sources = [], set()
    counts = {FAITHFUL: 0, HALLUCINATED: 0}
    for i in order:
        row = pool.loc[i]
        if counts[row.label] >= N_PER_LABEL or row.source in used_sources:
            continue
        picked.append(row)
        used_sources.add(row.source)
        counts[row.label] += 1
        if len(picked) == N_REAL:
            break

    trials = [
        {
            "trial_id": int(r.trial_id),
            "source": r.source,
            "summary": r.summary,
            "label": r.label,
            "is_catch": False,
        }
        for r in picked
    ]
    rng.shuffle(trials)
    catch_pos = rng.randint(1, N_REAL)  # never first
    trials.insert(catch_pos, {**CATCH_TRIAL, "is_catch": True})
    return trials


def should_terminate(catch_correct, quiz_attempts):
    return (not catch_correct) and quiz_attempts > MAX_QUIZ_ATTEMPTS_TOLERATED
