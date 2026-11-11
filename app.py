import html
import random
import time
from datetime import datetime, timezone

import streamlit as st

import storage
import study
from study import FAITHFUL, HALLUCINATED, LABELS, N_TOTAL

st.set_page_config(page_title="Summary fact-checking study", layout="wide")

st.markdown(
    """
    <style>
    .block-container { max-width: 1200px; }
    .doc { font-size: 1.05rem; line-height: 1.6; }
    .doc mark { background: #ffd8a8; color: inherit; padding: 0 2px; border-radius: 3px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    return study.load_dataset()


def now():
    return datetime.now(timezone.utc)


def render_text(text, highlight=None):
    """Show passage/summary text verbatim: escape HTML, keep line breaks, and stop
    '$' amounts from being rendered as LaTeX."""
    body = html.escape(str(text).strip())
    if highlight:
        span = html.escape(highlight)
        body = body.replace(span, f"<mark>{span}</mark>", 1)
    body = body.replace("$", "&#36;").replace("\n", "<br>")
    st.markdown(f'<div class="doc">{body}</div>', unsafe_allow_html=True)


def scroll_to_top(token):
    # Streamlit keeps the scroll position across reruns; jump to the top so each
    # new trial starts at the passage. `token` makes the snippet re-run per trial.
    st.iframe(
        f"<script>/*{token}*/window.parent.document.querySelector('section.main, "
        f"[data-testid=\"stMain\"]')?.scrollTo(0, 0);</script>",
        height=1,
    )


def init_state():
    """Set up a participant's session on their first script run."""
    if "stage" in st.session_state:
        return
    ss = st.session_state
    ss.stage = "instructions"  # -> quiz -> trials -> done | terminated
    ss.code = study.new_code()
    ss.started_at = now()
    ss.instructions_shown_at = time.time()
    ss.instructions_seconds = None
    ss.trials = study.sample_trials(load_data(), random.Random())
    ss.idx = 0
    ss.shown_at = {}
    ss.responses = []
    ss.quiz_attempts = 0
    ss.quiz_log = []
    ss.quiz_feedback = None
    ss.catch_correct = None
    ss.viewing = None


def session_record(status):
    ss = st.session_state
    real = [r for r in ss.responses if not r["is_catch"]]
    return {
        "participant_id": ss.code,
        "condition": study.CONDITION,
        "status": status,  # "completed" or "terminated"
        "started_at": ss.started_at,
        "finished_at": now(),
        "instructions_seconds": ss.instructions_seconds,
        "quiz_attempts": ss.quiz_attempts,
        "quiz_log": ss.quiz_log,
        "catch_correct": ss.catch_correct,
        # failed at least one attention check (kept, but worth excluding in analysis)
        "attention_flag": ss.catch_correct is False
        or ss.quiz_attempts > study.MAX_QUIZ_ATTEMPTS_TOLERATED,
        "n_real_trials": len(real),
        "n_real_correct": sum(r["correct"] for r in real),
        "assigned_trial_ids": [t["trial_id"] for t in ss.trials],
        "responses": ss.responses,
    }


def restart():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ---------------------------------------------------------------- callbacks


def finish_instructions():
    ss = st.session_state
    ss.instructions_seconds = round(time.time() - ss.instructions_shown_at, 2)
    ss.stage = "quiz"


def submit_trial():
    ss = st.session_state
    idx = ss.idx
    trial = ss.trials[idx]
    answer = ss[f"answer_{idx}"]
    correct = answer == trial["label"]
    ss.responses.append(
        {
            "position": idx + 1,
            "trial_id": trial["trial_id"],
            "is_catch": trial["is_catch"],
            "gold_label": trial["label"],
            "answer": answer,
            "correct": correct,
            "confidence": ss[f"confidence_{idx}"],
            "seconds": round(time.time() - ss.shown_at[idx], 2),
        }
    )

    if trial["is_catch"]:
        ss.catch_correct = correct
        if study.should_terminate(correct, ss.quiz_attempts):
            # save before switching screens, so a storage failure surfaces here
            storage.save(ss.code, session_record("terminated"))
            ss.stage = "terminated"
            return

    if idx + 1 == len(ss.trials):
        storage.save(ss.code, session_record("completed"))
        ss.stage = "done"
    else:
        ss.idx += 1


# ---------------------------------------------------------------- screens


def rule_box():
    st.info(
        "**The rule: judge the summary only against the passage.**\n\n"
        f"- **{FAITHFUL}**: every claim in the summary is supported by the passage. "
        "Rewording is fine as long as the meaning stays the same.\n"
        f"- **{HALLUCINATED}**: at least one claim in the summary contradicts the "
        "passage, or adds something the passage does not say, **even if it is true "
        "in the real world**.\n"
        "- Don't use your own knowledge. Something the passage says counts as "
        "supported even if you think it is wrong in reality."
    )


def instructions_screen():
    df = load_data()
    ex_f = df.loc[df.trial_id == study.EXAMPLE_FAITHFUL_ID].iloc[0]
    ex_h = df.loc[df.trial_id == study.EXAMPLE_HALLUCINATED_ID].iloc[0]

    st.title("Fact-checking AI-written summaries")
    st.write(
        "AI systems often write summaries that sound right but slip in details the "
        "original text never said. In this study you will check summaries like these."
    )
    st.markdown(
        f"You will see **{N_TOTAL} passages**, one at a time. Each one comes with a "
        "summary written by an AI. For each one:\n"
        f"1. Read the passage and the summary, then decide whether the summary is "
        f"**{FAITHFUL}** or **{HALLUCINATED}**.\n"
        "2. Say how confident you are, from **50** (a pure guess) to **100** "
        "(completely certain).\n\n"
        "Answers can't be changed once submitted. The study takes about **8 minutes**. "
        "Please work carefully: some passages include simple checks to confirm "
        "you are paying attention."
    )
    rule_box()

    st.subheader("Examples")
    st.caption("Two summaries of the same passage.")
    with st.container(border=True):
        st.markdown("**Passage**")
        render_text(ex_f.source)
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown(f"**Summary A**: :green[{FAITHFUL}]")
        render_text(ex_f.summary)
        st.caption("Both facts are stated exactly as in the passage.")
    with right, st.container(border=True):
        st.markdown(f"**Summary B**: :red[{HALLUCINATED}]")
        render_text(ex_h.summary, highlight=study.EXAMPLE_HALLUCINATED_SPAN)
        st.caption(study.EXAMPLE_HALLUCINATED_REASON)

    st.button(
        "I've read the instructions: continue",
        type="primary",
        on_click=finish_instructions,
        use_container_width=True,
    )

    # returning participants can look up what they submitted last time
    st.divider()
    st.markdown("**Already participated?**")
    code = st.text_input(
        "Enter your access code to view your previous responses",
        max_chars=study.CODE_LENGTH,
        placeholder=study.CODE_LENGTH * "X",
    ).strip().upper()
    if st.button("View my responses", disabled=not code):
        record = storage.load(code)
        if record is None or record.get("status") != "completed":
            st.error("We couldn't find that code. Check it and try again.")
        else:
            st.session_state.viewing = record
            st.rerun()


def quiz_screen():
    ss = st.session_state
    st.title("Quick check")
    st.write(
        "Before starting, answer these two questions about the rule. "
        "(You can retry if you get one wrong.)"
    )

    if ss.quiz_feedback:
        st.error(ss.quiz_feedback)
        rule_box()

    with st.form("quiz"):
        answers = {
            q["key"]: st.radio(q["question"], LABELS, index=None, key=f"quiz_{q['key']}")
            for q in study.QUIZ
        }
        submitted = st.form_submit_button("Check answers", type="primary")

    if submitted:
        if any(a is None for a in answers.values()):
            st.warning("Please answer both questions.")
            return
        wrong = [q for q in study.QUIZ if answers[q["key"]] != q["answer"]]
        ss.quiz_attempts += 1
        ss.quiz_log.append(
            {"attempt": ss.quiz_attempts, "answers": answers, "all_correct": not wrong}
        )
        if wrong:
            ss.quiz_feedback = (
                f"{len(wrong)} of your answers {'is' if len(wrong) == 1 else 'are'} "
                "incorrect. Please re-read the rule below and try again."
            )
        else:
            ss.quiz_feedback = None
            ss.stage = "trials"
        st.rerun()


def trial_screen():
    ss = st.session_state
    idx = ss.idx
    trial = ss.trials[idx]
    ss.shown_at.setdefault(idx, time.time())  # timer starts on first render of a trial
    scroll_to_top(idx)

    st.progress(idx / N_TOTAL, text=f"Passage {idx + 1} of {N_TOTAL}")
    with st.expander("Show the rule again"):
        rule_box()

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.markdown("**Passage**")
        render_text(trial["source"])
    with right, st.container(border=True):
        st.markdown("**AI-written summary**")
        render_text(trial["summary"])

    with st.container(border=True):
        answer = st.radio(
            "Is the summary faithful to the passage?",
            LABELS,
            index=None,
            horizontal=True,
            key=f"answer_{idx}",
        )
        confidence = st.radio(
            "How confident are you in your answer?",
            study.CONFIDENCE_LEVELS,
            index=None,
            horizontal=True,
            key=f"confidence_{idx}",
            format_func=lambda c: {50: "50 (guess)", 100: "100 (certain)"}.get(c, str(c)),
        )
        st.button(
            "Submit and continue" if idx + 1 < N_TOTAL else "Submit and finish",
            type="primary",
            disabled=answer is None or confidence is None,
            on_click=submit_trial,
            use_container_width=True,
        )


def done_screen():
    st.success("Thanks for participating! Your responses have been saved.")
    st.write(
        "If you would like to view your responses later, enter this access code "
        "on the study's start page:"
    )
    st.code(st.session_state.code, language=None)


def terminated_screen():
    st.error(
        "This session has ended because the attention checks were not passed. "
        "Please restart the study and read each passage and summary carefully."
    )
    st.button("Restart the study", type="primary", on_click=restart)


def viewing_screen():
    record = st.session_state.viewing
    st.title("Your previous responses")
    for r in record["responses"]:
        with st.container(border=True):
            st.caption(f"Passage {r['position']} of {len(record['responses'])}")
            st.markdown(
                f"You answered **{r['answer']}** with confidence **{r['confidence']}**."
            )
    if st.button("Back"):
        st.session_state.viewing = None
        st.rerun()


# ---------------------------------------------------------------- main

init_state()

if not storage.using_firestore():
    st.warning("Dev mode: no Firestore credentials, saving to .local_sessions.json")

if st.session_state.viewing is not None:
    viewing_screen()
else:
    {
        "instructions": instructions_screen,
        "quiz": quiz_screen,
        "trials": trial_screen,
        "done": done_screen,
        "terminated": terminated_screen,
    }[st.session_state.stage]()
