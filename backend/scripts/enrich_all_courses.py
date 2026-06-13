"""
Enriches ALL courses in the dataset with AI-estimated difficulty and workload.

WHY this file exists vs. enrich_courses.py:
  enrich_courses.py was a quick experiment that scored a small CSC sample to
  validate the data shape. This script is the production run — it processes
  every course across all departments so the full dataset carries difficulty
  and workload metadata, not just a CS slice.

Three deliberate changes from the original:
  1. No sampling — every course in courses_slim.json is scored.
  2. Persona is an undeclared major student, not a CS student. Difficulty
     scores for a course like CSC108 look very different to someone who has
     never coded vs. someone who is already an average CS undergrad.
  3. Workload scale is 1–10 (not 1–5), giving finer resolution to distinguish
     e.g. a light 3-hr/week course from a moderate 5-hr/week one.

WHY the Batches API instead of synchronous calls:
  The previous version called client.messages.create() once per course in a
  blocking loop — each call waited for a response before moving to the next.
  For thousands of courses this was slow and accumulated rate-limit pressure.
  The Batches API instead accepts up to 100,000 requests in a single call,
  processes them all asynchronously (up to 24-hour turnaround), and returns
  results when done. Key practical benefit: 50% token cost reduction on every
  input and output token, plus no per-request latency stacking or rate-limit
  throttling mid-run. The tradeoff is that results aren't available immediately
  — the script polls for completion rather than processing courses one by one.

Run from the backend/ directory:
    python scripts/enrich_all_courses.py

Output lands on the desktop as courses_all_enriched.json so it stays out of
the repo and does NOT overwrite the CS-sample file from enrich_courses.py.
"""

import json
import os
import re
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from dotenv import load_dotenv

# Walk up from the script to find the .env file — dotenv searches parent
# directories automatically, so this works whether .env is in backend/ or root.
load_dotenv()

# Script lives at backend/scripts/, so parent.parent = backend/
COURSES_PATH = Path(__file__).parent.parent / "courses_slim.json"

# WHY a different filename: keeps this full-dataset run separate from the
# CSC-only sample so both files can coexist on the desktop for comparison.
OUTPUT_FILENAME = "courses_all_enriched.json"


def resolve_output_path(filename: str) -> Path:
    """
    Pick a writable output directory.

    WHY not Path.home() / "Desktop" alone: on Windows with OneDrive folder
    redirection, Desktop lives at ~/OneDrive/Desktop and ~/Desktop may not
    exist — open() then raises FileNotFoundError even though scoring succeeded.
    """
    candidates = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
        Path(__file__).parent.parent / "data",
    ]
    for directory in candidates:
        if directory.exists():
            return directory / filename
    # Last resort: create backend/data/ rather than fail after a long API run.
    fallback = candidates[-1]
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / filename


OUTPUT_PATH = resolve_output_path(OUTPUT_FILENAME)


def course_prefix(code: str) -> str:
    """
    Extract the department prefix from a UofT course code (e.g. CSC from CSC207H1).

    WHY a regex instead of joining all letters: codes end in H1/Y1/F/S, so
    "".join(c for c in code if c.isalpha()) yields CSCH/ABPY — never matching
    STEM_PREFIXES entries like CSC or ABP.
    """
    match = re.match(r"^([A-Za-z]+)", code)
    return match.group(1).upper() if match else ""


def build_prompt(course: dict) -> str:
    """
    Build the scoring prompt for a single course.

    WHY extracted as its own function: the Batches API requires constructing all
    requests before submitting any of them, so prompt-building must be separable
    from the API call itself. In the old synchronous version these were fused
    inside estimate_scores().
    """
    code = course.get("code", "")
    name = course.get("name", "")
    description = course.get("description", "").strip()
    prereqs = course.get("prerequisites", "").strip()

    # WHY the undeclared-major persona instead of a CS-student persona:
    # This dataset spans ALL departments (humanities, sciences, social sciences,
    # etc.). Calibrating for a CS student would wildly misrepresent difficulty
    # for non-technical courses — a philosophy seminar might look trivially easy
    # to a CS student but genuinely challenging to someone encountering academic
    # argument and close reading for the first time. An undeclared-major student
    # is the most neutral baseline that applies fairly across every department.
    return f"""You are estimating difficulty and weekly workload for a University of Toronto course planner.

Calibrate every score from the perspective of an AVERAGE UofT undeclared-major student — someone who:
- Has NOT declared a major and is still exploring what subjects interest them
- Has NO assumed programming, lab, or specialist background — may never have coded before and has no particular strength in any academic discipline yet
- Has a broad but shallow academic background: some high school math and science, possibly one or two first-year university courses, but no deep expertise in anything
- Is encountering most subject areas for the first time without specialist context to draw on
- Is NOT a top-10% student or a high-achieving specialist — think the typical first- or second-year student figuring out university
- Earns roughly a C+ (68%) on average, consistent with the typical grade distribution in UofT courses — use this as a calibration anchor for what "manageable with effort" actually looks like
- Experiences normal first- and second-year time pressure from multiple courses, extracurriculars, and adjustment to university life

Do NOT calibrate for the star student who breezes through everything, or the struggling student who finds every course hard. Aim for the middle of the bell curve.
Calibrate difficulty especially from the lens of someone encountering this subject for the first time, with no specialist context.
If your reasoning contains a semicolon, rewrite it without one before returning.

Course: {code} — {name}
Description: {description if description else "(no description available)"}
Prerequisites: {prereqs if prereqs else "None"}

Return ONLY a JSON object — no markdown fences, no extra text:
{{
  "difficulty": <integer 1–10>,
  "workload": <integer 1–10>,
  "reasoning": "<one sentence, no semicolons — explain the dominant factor only. COUNT your words before returning. If your reasoning exceeds 20 words, rewrite it shorter. Do not exceed 20 words under any circumstances.>"
}}

Difficulty scale (from the undeclared-major student's perspective):
  1–3 = introductory — little to no prior knowledge assumed; concepts are self-contained and approachable for any curious student
  4–6 = intermediate — builds on some foundation (high school math, prior first-year course, or general literacy in the subject); requires genuine engagement but is manageable with consistent effort
  7–9 = advanced — demands real disciplinary maturity or accumulated background that most students only develop over time; upper-year prerequisites are actually needed
  10  = graduate-level or unusually demanding even by 4th-year standards

Workload scale (hours per week outside of lecture/tutorial, for an average student):
  1–2  = very light  (≈1–3 hrs/week  — occasional readings or very small, infrequent assignments)
  3–4  = light       (≈3–5 hrs/week  — regular readings or short problem sets most weeks)
  5–6  = moderate    (≈6–9 hrs/week  — consistent weekly assignments with meaningful depth; a typical 300-level course)
  7–8  = heavy       (≈10–14 hrs/week — large projects, frequent deliverables, or difficult problem sets; most students feel real time pressure)
  9–10 = very heavy  (15+ hrs/week   — capstone or unusually output-intensive course; students routinely report it consuming most of their semester)

Calibration anchors for workload:
  A first-year survey course with weekly readings and one essay per month   → 2
  A 200-level course with biweekly assignments and one midterm paper        → 4
  A 300-level course with a multi-week project and demanding problem sets   → 6
  A mid-level STEM course (e.g. a 300-level CS/math/physics course) with weekly
    problem sets, a lab or coding component every 1–2 weeks, and a multi-week
    project due near the end of term — the kind of course where a typical student
    spends 10–12 hrs/week between debugging, derivations, and write-ups          → 7
  A 400-level seminar with weekly response papers and a major research essay→ 8
  A capstone or intensive lab course requiring sustained full-semester output→ 9
Use these anchors to sanity-check your estimate. Err toward the lower end of each band when uncertain — it is better to underestimate slightly than to inflate scores.

Remember the reason IS NO MORE THAN 20 WORDS."""


def parse_scores(raw: str) -> dict[str, int | str | None]:
    """
    Parse Claude's JSON response into structured difficulty/workload scores.

    WHY a standalone function: both the batch result loop and any future
    debugging path need the same fence-stripping and error-fallback logic.
    Extracting it prevents duplication.
    """
    # Strip markdown fences defensively — Haiku sometimes adds them anyway
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        parsed = json.loads(raw)
        return {
            "difficulty": int(parsed["difficulty"]),
            "workload": int(parsed["workload"]),
            "difficulty_reasoning": str(parsed.get("reasoning", "")),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        # Store the raw text so we can debug bad responses without re-running
        return {
            "difficulty": None,
            "workload": None,
            "difficulty_reasoning": f"PARSE_ERROR: {raw[:200]}",
        }


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set — add it to your .env file or environment"
        )

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Loading courses from {COURSES_PATH}")
    with open(COURSES_PATH, encoding="utf-8") as f:
        all_courses: list[dict] = json.load(f)

    # ── SAMPLE MODE (optional) ────────────────────────────────────────────────
    # Set SAMPLE_MODE = True to score one random course per department (max 10)
    # instead of the full catalog — useful for prompt tuning without full API cost.
    SAMPLE_MODE = False
    STEM_ONLY_SAMPLE = False
    STEM_PREFIXES = {
        "CSC", "MAT", "STA", "PHY", "CHM", "BIO", "BCH", "EEB", "PSY",
        "ENV", "ESS", "AST", "ECE", "MSE", "CHE", "MIE", "CIV", "BME",
        "APS", "MGY", "IMM", "HMB", "ANT", "GGR", "PCL", "JEE",
    }

    if SAMPLE_MODE:
        import random

        seen_prefixes: set[str] = set()
        sampled: list[dict] = []
        shuffled = all_courses[:]
        random.shuffle(shuffled)

        if STEM_ONLY_SAMPLE:
            shuffled = [
                c for c in shuffled
                if course_prefix(c.get("code", "")) in STEM_PREFIXES
            ]

        for course in shuffled:
            prefix = course_prefix(course.get("code", ""))
            if prefix and prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                sampled.append(course)
            if len(sampled) == 10:
                break
        all_courses = sampled
    # ── END SAMPLE MODE ───────────────────────────────────────────────────────

    print(f"\nBuilding {len(all_courses)} batch requests...")

    # WHY we build all requests before submitting any: the Batches API is a
    # single call that takes the full list up front. This differs from the old
    # synchronous approach where each course triggered its own API call. Here
    # we front-load all the prompt construction, then hand everything off at once.
    requests: list[Request] = []
    for i, course in enumerate(all_courses):
        requests.append(
            Request(
                # WHY numeric index as custom_id: course codes can contain
                # characters (slashes, dots) that may violate the Batches API's
                # ID validation, and some cross-listed codes appear twice. A
                # simple sequential index is always valid and unique.
                custom_id=f"course-{i}",
                params=MessageCreateParamsNonStreaming(
                    model="claude-haiku-4-5",
                    max_tokens=300,
                    messages=[{"role": "user", "content": build_prompt(course)}],
                ),
            )
        )

    # Submit the entire set in one call — Anthropic queues and processes async.
    # WHY one call instead of many: beyond the 50% cost discount, batching
    # eliminates per-request network overhead and means we never hit the
    # per-minute rate limit that would throttle a large synchronous loop.
    print(f"Submitting batch of {len(requests)} courses to the Batches API...")
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch ID : {batch.id}")
    print(f"Status   : {batch.processing_status}")
    print("Polling every 60 s until the batch ends (most batches finish in < 1 hr)...")

    # WHY polling instead of webhooks: this is a one-shot CLI script, not a
    # server. A simple sleep-and-check loop is the right tool here. The SDK
    # handles any transient HTTP errors on the retrieve call automatically.
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        print(
            f"  {batch.processing_status} — "
            f"processing: {counts.processing}  "
            f"succeeded: {counts.succeeded}  "
            f"errored: {counts.errored}"
        )
        if batch.processing_status == "ended":
            break
        time.sleep(60)

    print(f"\nBatch ended — {counts.succeeded} succeeded, {counts.errored} errored")

    # Stream results out of the batch. WHY results() instead of paginating
    # manually: the SDK's results() method handles the server-sent results file
    # transparently, yielding one BetaMessageBatchIndividualResponse per course.
    results_map: dict[str, dict] = {}
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            raw = result.result.message.content[0].text.strip()
            results_map[result.custom_id] = parse_scores(raw)
        else:
            # WHY not raising here: a single bad request shouldn't abort the
            # entire run after a potentially long batch wait. We record None
            # scores so callers can identify and retry specific failures without
            # resubmitting everything.
            results_map[result.custom_id] = {
                "difficulty": None,
                "workload": None,
                "difficulty_reasoning": f"BATCH_ERROR: {result.result.type}",
            }

    # Merge scores back into the original course list, preserving order.
    # WHY not iterate results_map directly: the batch returns results in
    # arbitrary order; we want the output file to match the input order.
    enriched: list[dict] = []
    for i, course in enumerate(all_courses):
        custom_id = f"course-{i}"
        scores = results_map.get(
            custom_id,
            {
                "difficulty": None,
                "workload": None,
                "difficulty_reasoning": "MISSING_RESULT",
            },
        )
        code = course.get("code", "")
        if scores["difficulty"] is not None:
            print(
                f"  {code}: difficulty={scores['difficulty']}/10  "
                f"workload={scores['workload']}/10  — "
                f"{scores['difficulty_reasoning']}"
            )
        else:
            print(f"  {code}: ERROR — {scores['difficulty_reasoning']}")
        enriched.append({**course, **scores})

    output_path = resolve_output_path(OUTPUT_FILENAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(enriched)} enriched courses → {output_path}")


if __name__ == "__main__":
    main()
