"""
Enriches a sample of courses with AI-estimated difficulty and workload.

Uses Claude Haiku to estimate how intellectually demanding a course is (1-10)
and how many hours per week it typically demands (1-5). This data will
eventually power recommendations like "this is a heavy semester" warnings.

Run from the backend/ directory:
    python scripts/enrich_courses.py

Output lands on the desktop as courses_enriched.json so it stays out of
the repo while we're experimenting with the data shape.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Walk up from the script to find the .env file — dotenv searches parent
# directories automatically, so this works whether .env is in backend/ or root.
load_dotenv()

# Script lives at backend/scripts/, so parent.parent = backend/
COURSES_PATH = Path(__file__).parent.parent / "courses_slim.json"
OUTPUT_PATH = Path.home() / "Desktop" / "courses_enriched.json"

# How many courses to take from each year level.
# Slightly more from years 1-2 because introductory CSC courses vary a lot
# (some are math-heavy, some are coding-only) and we want that spread.
SAMPLES_PER_YEAR = {1: 3, 2: 3, 3: 2, 4: 2}


def get_course_year(code: str) -> int | None:
    """
    Extract year level from a UofT course code.

    WHY return None for year-0 codes: courses like CSC099Y1 are orientation/
    community courses with no academic difficulty to estimate. Excluding them
    keeps the sample meaningful and avoids confusing the model with edge cases.
    """
    m = re.search(r"[A-Za-z]{2,4}(\d)\d{2}", code)
    if m:
        yr = int(m.group(1))
        return yr if yr in (1, 2, 3, 4) else None
    return None


def select_sample_courses(all_courses: list[dict]) -> list[dict]:
    """
    Pick SAMPLES_PER_YEAR CSC courses from each year level.

    WHY prefer courses with descriptions: a blank description field means
    Claude has almost no signal to work with — it would essentially be
    guessing from the course name alone, which produces unreliable scores.
    """
    by_year: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}

    for course in all_courses:
        code = course.get("code", "")
        if not code.startswith("CSC"):
            continue
        year = get_course_year(code)
        if year in by_year:
            by_year[year].append(course)

    selected: list[dict] = []
    for year, quota in SAMPLES_PER_YEAR.items():
        candidates = by_year[year]
        # Put courses with non-empty descriptions first
        candidates.sort(key=lambda c: 0 if c.get("description") else 1)
        selected.extend(candidates[:quota])

    return selected


def estimate_scores(
    client: anthropic.Anthropic,
    course: dict,
) -> dict[str, int | str | None]:
    """
    Ask Claude Haiku to score a course on difficulty and weekly workload.

    WHY ask for JSON directly (not wrapped in markdown): we parse
    programmatically; asking for bare JSON is simpler than stripping fences,
    and Haiku reliably follows this instruction when told explicitly.

    WHY include prerequisites in the prompt: a course titled "Advanced
    Topics in X" has very different difficulty if its prereq is CSC108 vs
    CSC369 — the prereq chain is often the strongest difficulty signal.
    """
    code = course.get("code", "")
    name = course.get("name", "")
    description = course.get("description", "").strip()
    prereqs = course.get("prerequisites", "").strip()

    prompt = f"""You are estimating difficulty and weekly workload for a University of Toronto CS course planner.

Course: {code} — {name}
Description: {description if description else "(no description available)"}
Prerequisites: {prereqs if prereqs else "None"}

Return ONLY a JSON object — no markdown fences, no extra text:
{{
  "difficulty": <integer 1–10>,
  "workload": <integer 1–5>,
  "reasoning": "<one sentence explaining the estimate>"
}}

Difficulty scale:
  1–3 = introductory, light math, no prior CS assumed
  4–6 = intermediate, some proofs or systems concepts required
  7–9 = advanced, significant mathematical maturity or prior upper-year courses needed
  10  = graduate-level or unusually demanding

Workload scale:
  1 = light     (2–4 hrs/week outside class)
  2 = moderate  (4–6 hrs/week)
  3 = standard  (6–8 hrs/week)
  4 = heavy     (8–12 hrs/week)
  5 = very heavy (12+ hrs/week, e.g. project-intensive capstone)"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

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

    sample = select_sample_courses(all_courses)

    print(f"\nSelected {len(sample)} courses for enrichment:")
    for c in sample:
        yr = get_course_year(c["code"])
        print(f"  Year {yr}  {c['code']:<12} {c['name']}")

    enriched: list[dict] = []
    for i, course in enumerate(sample, 1):
        code = course.get("code", "")
        print(f"\n[{i}/{len(sample)}] Scoring {code}...")

        scores = estimate_scores(client, course)

        if scores["difficulty"] is not None:
            print(f"  difficulty={scores['difficulty']}/10  workload={scores['workload']}/5")
        else:
            print(f"  ERROR: {scores['difficulty_reasoning']}")

        print(f"  {scores['difficulty_reasoning']}")

        enriched.append({**course, **scores})

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(enriched)} enriched courses → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
