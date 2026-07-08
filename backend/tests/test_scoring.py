"""
Tests for _find_courses_by_code in scoring.py.

Covers the "MAT235/236" shorthand bug: students write course-code lists like
"MAT235/236" expecting both courses to be recognized, but the code-matching
regex only attaches subject letters to the first number in the slash — a bare
"236" with no letters was silently dropped from the AI's course context.
"""
from scoring import _find_courses_by_code, courses


def _codes(message: str) -> list[str]:
    return sorted(course.get_course_code() for course, _ in _find_courses_by_code(message, courses))


def test_shorthand_slash_expands_to_all_referenced_courses():
    assert _codes("MAT235/236 vs MAT237") == ["MAT235H1", "MAT236H1", "MAT237Y1"]


def test_chained_shorthand_expands_every_segment():
    assert _codes("MAT235/236/237") == ["MAT235H1", "MAT236H1", "MAT237Y1"]


def test_full_codes_separated_by_slash_still_match_independently():
    # regression: shorthand expansion must not interfere with codes that
    # already carry their own letters on both sides of the slash
    assert _codes("CSC108H1/CSC148H1") == ["CSC108H1", "CSC148H1"]


def test_single_code_with_no_slash_still_matches():
    assert _codes("is CSC148 hard?") == ["CSC148H1"]
