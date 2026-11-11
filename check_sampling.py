"""Sanity-check trial sampling over many simulated participants.

Usage: python check_sampling.py
"""

import collections
import random

import study

df = study.load_dataset()
pool = study.sampling_pool(df)
example_sources = set(df.source) - set(pool.source)
coverage = collections.Counter()

for seed in range(5000):
    trials = study.sample_trials(df, random.Random(seed))
    real = [t for t in trials if not t["is_catch"]]
    assert len(trials) == study.N_TOTAL
    assert sum(t["is_catch"] for t in trials) == 1 and not trials[0]["is_catch"]
    assert collections.Counter(t["label"] for t in real) == {
        study.FAITHFUL: study.N_PER_LABEL, study.HALLUCINATED: study.N_PER_LABEL}
    assert len({t["source"] for t in real}) == study.N_REAL, "repeated passage"
    assert not {t["source"] for t in real} & example_sources, "example passage leaked"
    coverage.update(t["trial_id"] for t in real)

print(f"OK: 5000 participants, pool = {len(pool)} of {len(df)} rows "
      f"({len(example_sources)} example passage(s) excluded)")
print(f"trials ever shown: {len(coverage)} / {len(pool)}; "
      f"times shown min/max: {min(coverage.values())}/{max(coverage.values())}")
