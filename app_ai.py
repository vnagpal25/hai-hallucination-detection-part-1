"""AI-assisted condition of the summary fact-checking study.

Same task, sampling, quiz, and attention-check rules as the baseline (app.py),
plus a two-stage trial: the participant answers alone first, then sees the saved
Assignment 2 AI output (verdict + highlighted phrase) and gives a final answer.
Sessions go to the "ai_sessions" Firestore collection.
"""

import html
import random
import time
from datetime import datetime, timezone

import streamlit as st

import storage
import study
from study import FAITHFUL, HALLUCINATED, LABELS, N_TOTAL

COLLECTION = study.AI_COLLECTION

st.set_page_config(page_title="Summary fact-checking study", layout="wide")

st.markdown(
    """
    <style>
    .block-container { max-width: 1200px; }
    .doc { font-size: 1.05rem; line-height: 1.6; }
    .doc mark { background: #ffd8a8; color: inherit; padding: 0 2px; border-radius: 3px; }
    .doc mark.ai, mark.ai { background: #bcd7ff; color: inherit; padding: 0 2px;
        border-radius: 3px; border-bottom: 2px solid #2f6fd6; }
    .ai-card { border: 2px solid #2f6fd6; border-radius: 8px; padding: 0.7rem 1rem;
        margin-top: 0.5rem; background: rgba(47, 111, 214, 0.06); }
    .ai-card .verdict { font-size: 1.25rem; font-weight: 700; }
    .ai-card .note { font-size: 0.9rem; opacity: 0.8; margin-top: 0.3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    return study.load_ai_dataset()


def now():
    return datetime.now(timezone.utc)


def render_text(text, highlight=None, css_class=None):
    """Show passage/summary text verbatim: escape HTML, keep line breaks, and stop
    '$' amounts from being rendered as LaTeX."""
    body = html.escape(str(text).strip())
    if highlight:
        span = html.escape(highlight)
        cls = f' class="{css_class}"' if css_class else ""
        body = body.replace(span, f"<mark{cls}>{span}</mark>", 1)
    body = body.replace("$", "&#36;").replace("\n", "<br>")
    st.markdown(f'<div class="doc">{body}</div>', unsafe_allow_html=True)


def ai_card(verdict, has_span, note=None):
    if note is None:
        note = (
            "The AI's suspected problem is highlighted in blue in the summary."
            if verdict == HALLUCINATED and has_span
            else "The AI did not find a problem in this summary."
        )
    color = "#c92a2a" if verdict == HALLUCINATED else "#2b8a3e"
    st.markdown(
        f'<div class="ai-card">🤖 AI suggestion<br>'
        f'<span class="verdict" style="color:{color}">{verdict}</span>'
        f'<div class="note">{html.escape(note)}</div></div>',
        unsafe_allow_html=True,
    )


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
    ss.stage = "instructions"  # -> quiz -> trials -> survey -> done | terminated
    ss.code = study.new_code()
    ss.started_at = now()
    ss.instructions_shown_at = time.time()
    ss.instructions_seconds = None
    trials = study.sample_trials(load_data(), random.Random())
    ss.trials = [
        {**t, **study.CATCH_AI_OUTPUT} if t["is_catch"] else t for t in trials
    ]
    ss.idx = 0
    ss.shown_at = {}  # trial idx -> time stage 1 was first shown
    ss.initial = {}  # trial idx -> stage-1 answer, filled when stage 1 is submitted
    ss.responses = []
    ss.quiz_attempts = 0
    ss.quiz_log = []
    ss.quiz_feedback = None
    ss.catch_correct = None
    ss.survey_answers = None
    ss.viewing = None


def session_record(status):
    ss = st.session_state
    real = [r for r in ss.responses if not r["is_catch"]]
    return {
        "participant_id": ss.code,
        "condition": study.AI_CONDITION,
        "status": status,  # "completed" or "terminated"
        "started_at": ss.started_at,
        "finished_at": now(),
        "instructions_seconds": ss.instructions_seconds,
        "quiz_attempts": ss.quiz_attempts,
        "quiz_log": ss.quiz_log,
        "catch_correct": ss.catch_correct,
        "attention_flag": ss.catch_correct is False
        or ss.quiz_attempts > study.MAX_QUIZ_ATTEMPTS_TOLERATED,
        "n_real_trials": len(real),
        "n_real_correct": sum(r["correct"] for r in real),  # final answers
        "n_real_initial_correct": sum(r["initial_correct"] for r in real),
        "n_ai_correct": sum(r["ai_correct"] for r in real),
        "n_switched": sum(r["switched"] for r in real),
        "assigned_trial_ids": [t["trial_id"] for t in ss.trials],
        "survey": ss.survey_answers,
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


def submit_initial():
    """Stage 1: lock in the participant's own answer, then reveal the AI."""
    ss = st.session_state
    idx = ss.idx
    trial = ss.trials[idx]
    answer = ss[f"answer_{idx}"]
    t = time.time()
    ss.initial[idx] = {
        "answer": answer,
        "confidence": ss[f"confidence_{idx}"],
        "seconds": round(t - ss.shown_at[idx], 2),
        "revealed_at": t,
    }

    if trial["is_catch"]:
        # scored before the AI is shown, so agreeing with the AI can't pass it
        ss.catch_correct = answer == trial["label"]
        if study.should_terminate(ss.catch_correct, ss.quiz_attempts):
            ss.responses.append(make_response(idx, answer, ss.initial[idx]["confidence"], t))
            storage.save(ss.code, session_record("terminated"), COLLECTION)
            ss.stage = "terminated"


def make_response(idx, final_answer, final_confidence, t):
    ss = st.session_state
    trial = ss.trials[idx]
    init = ss.initial[idx]
    gold, ai = trial["label"], trial["ai_verdict"]
    ai_correct = ai == gold
    switched = final_answer != init["answer"]
    final_seconds = round(t - init["revealed_at"], 2)
    return {
        "position": idx + 1,
        "trial_id": trial["trial_id"],
        "is_catch": trial["is_catch"],
        "gold_label": gold,
        "ai_verdict": ai,
        "ai_flagged_span": trial["ai_span"],
        "ai_correct": ai_correct,
        "initial_answer": init["answer"],
        "initial_correct": init["answer"] == gold,
        "initial_confidence": init["confidence"],
        "initial_seconds": init["seconds"],
        "final_answer": final_answer,
        "final_confidence": final_confidence,
        "final_seconds": final_seconds,
        # same names as the baseline, for cross-condition analysis (final answer,
        # total time on the trial)
        "answer": final_answer,
        "correct": final_answer == gold,
        "confidence": final_confidence,
        "seconds": round(init["seconds"] + final_seconds, 2),
        # reliance
        "agree_initial": init["answer"] == ai,
        "agree_final": final_answer == ai,
        "switched": switched,
        "switched_to_ai": switched and final_answer == ai,
        "over_reliance": switched and final_answer == ai and not ai_correct,
        "under_reliance": ai_correct and init["answer"] != ai and not switched,
    }


def submit_final():
    """Stage 2: record the final answer and move on."""
    ss = st.session_state
    idx = ss.idx
    ss.responses.append(
        make_response(
            idx, ss[f"final_answer_{idx}"], ss[f"final_confidence_{idx}"], time.time()
        )
    )
    if idx + 1 == len(ss.trials):
        ss.stage = "survey"
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


def ai_box():
    st.warning(
        "**About the AI assistant.** For each summary you will **first answer on your "
        "own**. Then an AI fact-checker's suggestion appears: its verdict "
        f"(**{FAITHFUL}** or **{HALLUCINATED}**) and, when it thinks the summary is "
        "hallucinated, the phrase it thinks is wrong highlighted in blue. You can then "
        "keep or change your answer.\n\n"
        "**The AI is often wrong.** In testing it was correct on only about **6 out of "
        "10** summaries, and it **misses many hallucinations** (it often says "
        f"{FAITHFUL} when the summary is actually {HALLUCINATED}). Treat it as a "
        "second opinion, not the answer."
    )


def instructions_screen():
    df = load_data()
    ex_f = df.loc[df.trial_id == study.EXAMPLE_FAITHFUL_ID].iloc[0]
    ex_h = df.loc[df.trial_id == study.EXAMPLE_HALLUCINATED_ID].iloc[0]

    st.title("Fact-checking AI-written summaries, with an AI assistant")
    st.write(
        "AI systems often write summaries that sound right but slip in details the "
        "original text never said. In this study you will check summaries like these, "
        "with help from an AI fact-checker."
    )
    st.markdown(
        f"You will see **{N_TOTAL} passages**, one at a time. Each one comes with a "
        "summary written by an AI. For each one:\n"
        f"1. Read the passage and the summary, then decide whether the summary is "
        f"**{FAITHFUL}** or **{HALLUCINATED}**, and say how confident you are, from "
        "**50** (a pure guess) to **100** (completely certain).\n"
        "2. See the AI assistant's suggestion, then give your **final** answer and "
        "confidence. You can keep or change your first answer.\n"
        "3. At the end, answer three short questions about the AI.\n\n"
        "Answers can't be changed once submitted. The study takes about **9 minutes**. "
        "Please work carefully: some passages include simple checks to confirm "
        "you are paying attention."
    )
    rule_box()
    ai_box()

    st.subheader("Examples")
    st.caption(
        "Two summaries of the same passage, with the AI's real suggestion for each. "
        "Note that the AI missed the problem in Summary B."
    )
    with st.container(border=True):
        st.markdown("**Passage**")
        render_text(ex_f.source)
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown(f"**Summary A**: :green[{FAITHFUL}]")
        render_text(ex_f.summary)
        st.caption("Both facts are stated exactly as in the passage.")
        ai_card(ex_f.model_verdict, False, note="The AI got this one right.")
    with right, st.container(border=True):
        st.markdown(f"**Summary B**: :red[{HALLUCINATED}]")
        render_text(ex_h.summary, highlight=study.EXAMPLE_HALLUCINATED_SPAN)
        st.caption(study.EXAMPLE_HALLUCINATED_REASON)
        ai_card(
            ex_h.model_verdict,
            False,
            note="The AI got this one wrong: it missed the invented connection.",
        )
    st.markdown(
        'When the AI says a summary is hallucinated, it highlights the phrase it '
        'suspects <mark class="ai">like this</mark>.',
        unsafe_allow_html=True,
    )

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
        record = storage.load(code, COLLECTION)
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


def confidence_label(c):
    return {50: "50 (guess)", 100: "100 (certain)"}.get(c, str(c))


def trial_screen():
    ss = st.session_state
    idx = ss.idx
    trial = ss.trials[idx]
    revealed = idx in ss.initial
    ss.shown_at.setdefault(idx, time.time())  # timer starts on first render of a trial
    scroll_to_top(idx)

    step = "Step 2 of 2: AI suggestion" if revealed else "Step 1 of 2: your own answer"
    st.progress(idx / N_TOTAL, text=f"Passage {idx + 1} of {N_TOTAL} · {step}")
    with st.expander("Show the rule again"):
        rule_box()

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.markdown("**Passage**")
        render_text(trial["source"])
    with right:
        with st.container(border=True):
            st.markdown("**AI-written summary**")
            if revealed and trial["ai_verdict"] == HALLUCINATED:
                render_text(trial["summary"], highlight=trial["ai_span"], css_class="ai")
            else:
                render_text(trial["summary"])
        if revealed:
            ai_card(trial["ai_verdict"], bool(trial["ai_span"]))

    with st.container(border=True):
        if not revealed:
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
                format_func=confidence_label,
            )
            st.button(
                "Submit and see the AI's suggestion",
                type="primary",
                disabled=answer is None or confidence is None,
                on_click=submit_initial,
                use_container_width=True,
            )
        else:
            init = ss.initial[idx]
            st.markdown(
                f"Your first answer: **{init['answer']}** "
                f"(confidence {init['confidence']}). Keep it or change it below."
            )
            st.radio(
                "Final answer: is the summary faithful to the passage?",
                LABELS,
                index=LABELS.index(init["answer"]),
                horizontal=True,
                key=f"final_answer_{idx}",
            )
            st.radio(
                "How confident are you in your final answer?",
                study.CONFIDENCE_LEVELS,
                index=study.CONFIDENCE_LEVELS.index(init["confidence"]),
                horizontal=True,
                key=f"final_confidence_{idx}",
                format_func=confidence_label,
            )
            st.button(
                "Submit final answer" + (" and continue" if idx + 1 < N_TOTAL else ""),
                type="primary",
                on_click=submit_final,
                use_container_width=True,
            )


def survey_screen():
    ss = st.session_state
    st.title("Almost done: three questions about the AI")
    st.write("How much do you agree with each statement? (1 = strongly disagree, "
             "7 = strongly agree)")
    with st.form("survey"):
        answers = {
            item["key"]: st.radio(
                item["statement"],
                study.LIKERT,
                index=None,
                horizontal=True,
                key=f"survey_{item['key']}",
                format_func=lambda v: {1: "1 (strongly disagree)",
                                       7: "7 (strongly agree)"}.get(v, str(v)),
            )
            for item in study.SURVEY
        }
        submitted = st.form_submit_button("Submit and finish", type="primary")

    if submitted:
        if any(a is None for a in answers.values()):
            st.warning("Please answer all three questions.")
            return
        ss.survey_answers = answers
        # save before switching screens, so a storage failure surfaces here
        storage.save(ss.code, session_record("completed"), COLLECTION)
        ss.stage = "done"
        st.rerun()


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
                f"First answer **{r['initial_answer']}** ({r['initial_confidence']}), "
                f"AI suggested **{r['ai_verdict']}**, final answer "
                f"**{r['final_answer']}** ({r['final_confidence']})."
            )
    if st.button("Back"):
        st.session_state.viewing = None
        st.rerun()


# ---------------------------------------------------------------- main

init_state()

if not storage.using_firestore():
    st.warning(
        f"Dev mode: no Firestore credentials, saving to "
        f"{storage.local_path(COLLECTION).name}"
    )

if st.session_state.viewing is not None:
    viewing_screen()
else:
    {
        "instructions": instructions_screen,
        "quiz": quiz_screen,
        "trials": trial_screen,
        "survey": survey_screen,
        "done": done_screen,
        "terminated": terminated_screen,
    }[st.session_state.stage]()
