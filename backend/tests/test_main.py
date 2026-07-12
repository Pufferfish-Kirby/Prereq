"""
Tests for main.py's graceful degradation when the Voyage embedding call fails.

Mocks the search functions main.py calls (the seam between main.py and the
retrieval layer) rather than the Voyage client itself, since these tests are
about main.py's own error handling, not embeddings.py's.
"""
from unittest.mock import patch

import voyageai

import main


def test_build_course_context_degrades_to_empty_string_on_voyage_failure():
    with patch("main.search_by_message", side_effect=voyageai.error.APIConnectionError("boom")):
        result = main._build_course_context("what are some easy CS courses")

    assert result == ""


def test_build_program_context_degrades_to_empty_on_voyage_failure():
    with patch(
        "main.search_programs_by_message", side_effect=voyageai.error.APIConnectionError("boom")
    ):
        context, matched_programs = main._build_program_context("computer science major")

    assert context == ""
    assert matched_programs == []
