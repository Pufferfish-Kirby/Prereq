"""
clean_course_html.py — One-time script to strip leftover HTML from course text fields.

WHY this exists:
    The TTB scraper (data_pulling.py) pulls description/prerequisite/etc. text
    straight from the calendar's rich-text fields, so tags like <p>, <strong>,
    and <a href="..."> ride along into courses_slim.json and, from there, into
    courses_all_enriched.json (the file scoring.py actually loads at runtime).
    Those tags are meaningless to both students reading a rendered chat bubble
    and to Claude, which just sees literal "<p>" characters as noise in the
    system prompt.

WHY html.parser instead of a regex or adding BeautifulSoup as a dependency:
    A regex like re.sub(r'<[^>]+>', '', text) breaks on '<' inside an
    unclosed/malformed tag or an <a href="..."> where the URL is fine but the
    surrounding tag isn't a simple "<word>" shape. html.parser is in the
    standard library, handles malformed markup gracefully, and lets us also
    unescape entities (&amp; -> &) in the same pass.

WHY both courses_slim.json and courses_all_enriched.json:
    enrich_all_courses.py reads courses_slim.json and adds AI-generated
    fields (difficulty, workload, tags) on top of it to produce
    courses_all_enriched.json — it never modifies the scraped text fields.
    Re-running the enrichment step just to get clean text would mean paying
    for ~3200 Claude calls again for no reason, so we patch both files with
    the same stripping logic instead and keep them in sync.

Usage (from inside backend/):
    python clean_course_html.py
"""
from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

# Fields known to contain scraped rich-text (verified via manual inspection —
# 'description' and 'name' were already clean, so they're left untouched).
_TEXT_FIELDS = ["prerequisites", "corequisites", "exclusions", "recommended_preparation"]

_FILES = ["courses_slim.json", "courses_all_enriched.json"]


class _TagStripper(HTMLParser):
    """Collects only the text data between tags, dropping the tags themselves."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # auto-unescapes &amp; etc.
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities, collapsing whitespace left behind."""
    if not text or "<" not in text:
        # Fast path: most fields (and every field on most courses) have no
        # markup at all, so skip the parser entirely when there's no '<'.
        return text

    parser = _TagStripper()
    parser.feed(text)
    cleaned = parser.get_text()

    # Tags like </p><p> leave two adjacent spaces / no space at all where a
    # paragraph break used to be — normalise all whitespace runs to one space
    # so sentences don't run together or end up oddly spaced.
    return " ".join(cleaned.split())


def clean_file(path: Path) -> None:
    with open(path, encoding="utf-8") as f:
        courses = json.load(f)

    changed = 0
    for course in courses:
        for field in _TEXT_FIELDS:
            value = course.get(field)
            if isinstance(value, str):
                new_value = strip_html(value)
                if new_value != value:
                    course[field] = new_value
                    changed += 1

    with open(path, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    print(f"{path.name}: cleaned {changed} field(s) across {len(courses)} courses")


if __name__ == "__main__":
    base_dir = Path(__file__).parent
    for filename in _FILES:
        file_path = base_dir / filename
        if not file_path.exists():
            print(f"Skipping {filename} — not found")
            continue
        clean_file(file_path)
