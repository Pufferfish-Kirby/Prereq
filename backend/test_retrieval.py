"""
Retrieval test script for semantic search validation.

Test different query formulations to compare results and understand
why some queries miss relevant courses. Includes:
  - Direct semantic search results with scores
  - Message-based search results
  - Side-by-side comparison of query variations
  - Course detail printing
"""

from scoring import search_by_message, courses, _extract_interests_from_text, _strip_filler
from embeddings import semantic_search


def print_course_details(code: str) -> None:
    """Print detailed info about a single course."""
    course = next((c for c in courses if c.get_course_code() == code), None)
    if not course:
        print(f"  Course {code} not found in database")
        return

    print(f"  Code: {code}")
    print(f"  Name: {course.get_name()}")
    print(f"  Tags: {', '.join(course.tags)}")
    print(f"  Desc: {course.description[:100]}...")


def test_semantic_search(query: str, top_n: int = 10) -> None:
    """Test the embedding-based semantic search directly."""
    print(f"\n{'='*80}")
    print(f"SEMANTIC SEARCH: \"{query}\"")
    print(f"{'='*80}")

    results = semantic_search(query, top_n=top_n)

    if not results:
        print("  (no results)")
        return

    print(f"\n  {'Score':<8} {'Code':<12} {'Course Name'}")
    print(f"  {'-'*70}")
    for code, score in results:
        course = next((c for c in courses if c.get_course_code() == code), None)
        if course:
            name = course.get_name()[:50]
            print(f"  {score:6.3f}   {code:<12} {name}")

    # Show detailed info for top 3
    print(f"\n  Top 3 Course Details:")
    print(f"  {'-'*70}")
    for code, _ in results[:3]:
        print_course_details(code)
        print()


def test_message_search(message: str, top_n: int = 10) -> None:
    """Test the message-based search (semantic + code lookup + interest extraction)."""
    print(f"\n{'='*80}")
    print(f"MESSAGE SEARCH: \"{message}\"")
    print(f"{'='*80}")

    # Show extracted interests
    interests = _extract_interests_from_text(message)
    print(f"\n  Extracted interests: {interests if interests else '(none)'}")

    # Run search
    results = search_by_message(message, courses, top_n=top_n)

    if not results:
        print("  (no results)")
        return

    print(f"\n  {'Score':<8} {'Code':<12} {'Course Name'}")
    print(f"  {'-'*70}")
    for course, score in results:
        name = course.get_name()[:50]
        print(f"  {score:6.2f}   {course.get_course_code():<12} {name}")

    # Show detailed info for top 3
    print(f"\n  Top 3 Course Details:")
    print(f"  {'-'*70}")
    for course, _ in results[:3]:
        print_course_details(course.get_course_code())
        print()


def compare_queries(query_set: list[str], top_n: int = 10) -> None:
    """
    Compare multiple query formulations side-by-side.
    Shows which courses appear in each result and which are unique/common.
    """
    print(f"\n{'='*80}")
    print(f"QUERY COMPARISON (top {top_n} for each)")
    print(f"{'='*80}\n")

    all_results = {}
    all_codes = set()

    for query in query_set:
        results = semantic_search(query, top_n=top_n)
        codes = [code for code, _ in results]
        all_results[query] = codes
        all_codes.update(codes)

    # Print results per query
    for i, query in enumerate(query_set, 1):
        codes = all_results[query]
        print(f"{i}. Query: \"{query}\"")
        for j, code in enumerate(codes, 1):
            course = next((c for c in courses if c.get_course_code() == code), None)
            if course:
                print(f"   {j:2d}. {code:<12} {course.get_name()[:55]}")
        print()

    # Show coverage statistics
    print(f"Coverage Statistics:")
    print(f"  Total unique courses across all queries: {len(all_codes)}")

    # Find courses that appear in all vs. some queries
    code_freq = {}
    for codes in all_results.values():
        for code in set(codes):
            code_freq[code] = code_freq.get(code, 0) + 1

    appears_in_all = [code for code, count in code_freq.items() if count == len(query_set)]
    appears_in_some = [code for code, count in code_freq.items() if 1 < count < len(query_set)]
    appears_once = [code for code, count in code_freq.items() if count == 1]

    print(f"  Appear in ALL {len(query_set)} queries: {len(appears_in_all)}")
    if appears_in_all:
        for code in appears_in_all[:5]:
            course = next((c for c in courses if c.get_course_code() == code), None)
            if course:
                print(f"    - {code}: {course.get_name()[:50]}")

    print(f"  Appear in SOME queries: {len(appears_in_some)}")
    print(f"  Appear in ONLY ONE query: {len(appears_once)}")


def dump_all_coding_courses() -> None:
    """For reference: list all courses with 'coding' or 'programming' in their description."""
    print(f"\n{'='*80}")
    print(f"ALL COURSES WITH 'CODING' OR 'PROGRAMMING' IN DESCRIPTION")
    print(f"{'='*80}\n")

    coding_courses = []
    for course in courses:
        text = (course.get_name() + " " + course.description).lower()
        if "coding" in text or "programming" in text:
            coding_courses.append(course)

    coding_courses.sort(key=lambda c: c.get_course_code())

    print(f"Found {len(coding_courses)} courses:\n")
    for course in coding_courses:
        print(f"  {course.get_course_code():<12} {course.get_name()}")

    return coding_courses


PROBLEM_QUERIES = [
    "coding courses for first year students",
    "Do you have any coding courses to recommend to a first year",
]


if __name__ == "__main__":
    print("\n" + "="*80)
    print("RETRIEVAL TEST SUITE — WITH STOP WORD STRIPPING")
    print("="*80)

    # 1. Show what the stop word stripper does to each problem query
    print("\n--- STOP WORD STRIPPING PREVIEW ---")
    for q in PROBLEM_QUERIES:
        stripped = _strip_filler(q)
        print(f"  Original : {q}")
        print(f"  Stripped : {stripped}")
        print()

    # 2. For each problem query: raw message search (now uses stripped query internally)
    print("\n--- MESSAGE SEARCH (stop-word-stripped internally) ---")
    for q in PROBLEM_QUERIES:
        test_message_search(q, top_n=10)

    # 3. Also test the stripped queries directly against semantic_search so we can
    #    see the raw similarity scores without the scoring.py wrapper
    print("\n--- DIRECT SEMANTIC SEARCH ON STRIPPED QUERIES ---")
    for q in PROBLEM_QUERIES:
        stripped = _strip_filler(q)
        test_semantic_search(stripped, top_n=10)

    # 4. Baseline: "introductory programming" should still work as before
    print("\n--- BASELINE (should still work) ---")
    test_semantic_search("introductory programming", top_n=10)

    # 5. Reference list of all coding courses in the DB
    all_coding = dump_all_coding_courses()

    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total courses in database: {len(courses)}")
    print(f"Courses with 'coding'/'programming' in text: {len(all_coding)}")
    print(f"Embedding model: all-MiniLM-L6-v2 (384-dim)")
