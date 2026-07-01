"""
verify_year_context_fix.py — throwaway verification script for the
program/course context wiring bug fix (see CLAUDE.md task notes).

Calls the context-building logic directly (no FastAPI, no Claude API call —
zero network cost) to confirm:
  1. A "second year computer science specialist" query now surfaces
     CSC236H1 and CSC263H1 (previously missing "not detailed in my info"
     courses) alongside the previously-present semantic-search hits.
  2. A query with NO year mentioned does NOT get bloated with the CS
     Specialist's full 60+ course codes — confirms the "only expand when a
     year is detected" guard actually holds.

Run from inside backend/:  python verify_year_context_fix.py
"""

from main import _build_course_context, _build_program_context
from scoring import _detect_year_level

PREVIOUSLY_MISSING = {"CSC236H1", "CSC263H1"}
PREVIOUSLY_PRESENT = {"CSC207H1", "CSC209H1", "CSC240H1", "CSC258H1", "CSC265H1"}
BONUS_EXPECTED = {"MAT223H1", "MAT240H1"}  # STA23x/24x/25x codes vary by program text


def run_case(label: str, message: str) -> str:
    print(f"\n=== {label} ===")
    print(f"message: {message!r}")

    year = _detect_year_level(message)
    print(f"detected year: {year}")

    program_context, matched_programs = _build_program_context(message)
    print(f"matched programs: {[p.program_code for p in matched_programs]}")

    extra_codes: set[str] = set()
    if year is not None:
        for prog in matched_programs:
            extra_codes.update(prog.get_course_codes_for_year(year))
    print(f"extra_codes ({len(extra_codes)}): {sorted(extra_codes)}")

    course_context = _build_course_context(message, extra_codes=extra_codes)
    print(course_context)
    return course_context


def main() -> None:
    # Case 1: year mentioned — should now include CSC236H1/CSC263H1.
    ctx = run_case(
        "second-year CS specialist (year DETECTED)",
        "what courses do I need to take as a second year computer science specialist",
    )
    for code in PREVIOUSLY_MISSING | PREVIOUSLY_PRESENT:
        status = "OK" if code in ctx else "MISSING"
        print(f"  {status}: {code}")
    for code in BONUS_EXPECTED:
        present = "present" if code in ctx else "absent (ok, bonus only)"
        print(f"  bonus {code}: {present}")

    missing_after_fix = [c for c in PREVIOUSLY_MISSING if c not in ctx]
    assert not missing_after_fix, f"Fix did not work, still missing: {missing_after_fix}"

    # Case 2: no year mentioned — should NOT be bloated with 60+ codes.
    ctx2 = run_case(
        "CS specialist, no year mentioned (year NOT detected)",
        "tell me about the computer science specialist",
    )
    course_lines = [l for l in ctx2.splitlines() if l.startswith("- ")]
    print(f"\ncourse lines in context: {len(course_lines)} (expect <= 5, top_n cap)")
    assert len(course_lines) <= 5, "No-year case unexpectedly bloated the course context!"

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
