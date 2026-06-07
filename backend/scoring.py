# ok this is where we will define our scoring system
import json
import re
from pathlib import Path

# Use __file__ so this works regardless of which directory the process is launched from.
# Without this, `open("courses_slim.json")` resolves against CWD, which breaks when
# build_embeddings.py or tests are run from the project root instead of backend/.
_DATA_FILE = Path(__file__).parent / "courses_slim.json"
with open(_DATA_FILE, "r", encoding="utf-8") as file:
    data = json.load(file)

class Course:
    def __init__(self,
        code: str,
        name: str,
        description: str,
        tags: list[str] | None = None,
        prerequisites: str | None = None,
        corequisites: str | None = None,
        credits: float = 0.5,
        workload: int = 3,
        difficulty: int = 5,
        rating: float | None = None,
        reviews: list[str] | None = None,
    ) -> None:
        self._code = code
        self._name = name
        self.tags = tags if tags is not None else []
        self.description = description
        self._prerequisites = prerequisites if prerequisites is not None else ""
        self._corequisites = corequisites if corequisites is not None else ""
        self._credits = credits
        self.workload = workload
        self.difficulty = difficulty
        self.rating = rating
        self.reviews = reviews if reviews is not None else []
    
    def get_course_code(self) -> str:
        return self._code
    def get_name(self) -> str:
        return self._name
    def get_prerequisites(self) -> list[str]:
        return self._prerequisites
    def get_corequisites(self) -> list[str]:
        return self._corequisites
    def get_credits(self) -> float:
        return self._credits
    def is_eligible(self, completed: list[str]) -> bool:
        return all(prereq in completed for prereq in self._prerequisites)

    def to_text(self) -> str:
        # Joins the most signal-rich fields into one string for embedding.
        # Code first so the model sees the department prefix (MAT, CSC, etc.)
        # before the name, giving code-prefix queries a strong anchor.
        tags_str = " | ".join(self.tags) if self.tags else ""
        return f"{self._code} {self._name}. {self.description} {tags_str}".strip()

class AcademicHistory:  # this is here once we can link the history to get courses they can take/can't take
    courses: list[Course]

    def __init__(self, courses: list[Course]) -> None:
        self._courses = courses

    def get_courses(self) -> list[Course]:
        return self._courses
    def add_course(self, course: Course) -> None:
        self._courses.append(course)

# Weightings
INTEREST_WEIGHT   = 0.35
WEIGHT_DIFFICULTY = 0.225
WEIGHT_WORKLOAD   = 0.225
WEIGHT_RATING     = 0.20

# Synonym map: when a student types a natural-language interest, expand it
# to the technical tags we use on courses. This bridges the gap between
# "coding" (what students say) and "programming" (what our tags say).
# Phase 2 will replace this with embedding-based similarity; for now a
# manually curated map is cheap, transparent, and easy to extend.
INTEREST_SYNONYMS: dict[str, list[str]] = {
    # General programming intents — these are the "hub" terms everything else maps to
    "coding":           ["programming", "python", "java", "software", "computing", "code", "computer",
                         "algorithms", "web", "javascript"],
    "programming":      ["coding", "python", "java", "software", "computing", "code", "computer",
                         "algorithms", "web", "javascript"],
    # Specific languages/technologies — map back to the hub so "python" == "coding" in matching power
    "python":           ["programming", "coding", "software", "computing", "code", "computer", "scripting"],
    "java":             ["programming", "coding", "software", "computing", "code", "computer", "object-oriented"],
    "javascript":       ["programming", "coding", "software", "web", "computing", "code", "computer"],
    "software":         ["programming", "coding", "python", "java", "computing", "code", "computer"],
    "computing":        ["programming", "coding", "python", "java", "software", "code", "computer"],
    "algorithms":       ["programming", "computing", "discrete", "complexity", "data structures", "problem"],
    "web":              ["programming", "software", "html", "css", "javascript", "frontend", "interface"],
    # Math family
    "math":             ["mathematics", "calculus", "algebra", "statistics", "analysis", "proofs", "proof",
                         "theorem", "discrete", "linear", "differential", "logic", "rigorous", "number theory"],
    "mathematics":      ["math", "calculus", "algebra", "statistics", "analysis", "proofs", "proof",
                         "theorem", "discrete", "linear", "differential", "logic", "rigorous"],
    "stats":            ["statistics", "probability", "analysis", "stochastic", "inference", "regression"],
    # Data / AI family
    "data":             ["statistics", "data science", "machine learning", "analysis", "python", "dataset"],
    "ai":               ["machine learning", "artificial intelligence", "neural", "deep learning",
                         "natural language", "computer vision", "reinforcement", "prediction"],
    "machine learning": ["ai", "artificial intelligence", "neural", "deep learning", "data",
                         "prediction", "statistics"],
    # Sciences
    "biology":          ["life sciences", "biochemistry", "molecular", "genetics", "cell"],
    "chemistry":        ["organic", "inorganic", "biochemistry", "molecular", "reactions"],
    "psychology":       ["behavior", "social-science", "mental", "cognition", "research"],
    # Humanities / Social
    "writing":          ["english", "literature", "composition", "rhetoric", "essay"],
    "history":          ["historical", "civilization", "political", "social"],
    "economics":        ["micro", "macro", "finance", "markets", "policy"],
    "business":         ["management", "finance", "marketing", "economics", "strategy"],
    # Other
    "design":           ["art", "visual", "creative", "ux", "interface"],
    "networks":         ["systems", "computer", "distributed", "internet", "protocol"],
    "security":         ["cryptography", "systems", "networks", "privacy", "cyber"],
}

# Scales for each field — used to normalize raw values to 0–10.
DIFFICULTY_MIN, DIFFICULTY_MAX = 1, 10   # course.difficulty range
WORKLOAD_MIN,   WORKLOAD_MAX   = 1, 5    # course.workload range
RATING_MIN,     RATING_MAX     = 1, 5    # course.rating range (e.g., UofT eval scale)

# When a course has no rating yet, we assume a neutral mid-point rather
# than penalizing it for lacking data.
RATING_NEUTRAL = (RATING_MIN + RATING_MAX) / 2

# JSON TO COURSE CONVERSION
courses = []  
for c in data:
    # tags: department + breadth requirements give cheap topic signals without a tagging pipeline
    pseudo_tags = [c.get('department', '')] + c.get('breadth_requirements', [])
    courses.append(Course(
        c['code'],
        c['name'],           # English title e.g. "Calculus and Analysis I" — richest keyword source
        c['description'],
        tags=pseudo_tags,
        prerequisites=c['prerequisites'],
        corequisites=c['corequisites'],
        credits=c['credit_value'],
    ))

def _interest_score(course: "Course", interests: list[str]) -> float:
    """
    Score how well a course matches the student's interests (0–10).

    Matching works in two passes:
      1. Synonym expansion: "coding" expands to ["programming", "python", ...]
         so students don't need to know our internal tag vocabulary.
      2. Text search: each (expanded) interest term is checked against the
         course's tags AND its description words, case-insensitively.
         This catches cases where the tag doesn't exist but the description
         says "This course covers programming techniques…".

    WHY divide by interests length (not tags length):
        We want to reward courses that cover MANY of the student's interests,
        not just courses with few tags (which would make narrow courses look better).
        A course matching 2 out of 3 interests scores 6.67; one matching 1 out of 3
        scores 3.33 — proportional to how much of the student's agenda it covers.
    """
    if not interests:
        return 0.0

    # Search three fields separately so we can weight by signal strength.
    # WHY: a binary "anywhere in the text" match treats CSC108's title "Computer
    # Programming" the same as a chemistry course that incidentally mentions
    # "software" once in its description. Title hits are near-definitive;
    # description hits are weak evidence at best.
    title_blob = (course.get_name() + " " + course.get_course_code()).lower()
    tags_blob  = " ".join(course.tags).lower()        # department + breadth requirements
    desc_blob  = course.description.lower()

    # Per-field weights. Title=1.0 means a single title hit alone gives full
    # credit for that interest; description=0.4 means a description-only hit
    # is real but soft evidence. Tags (department) sit in between.
    TITLE_W, TAGS_W, DESC_W = 1.0, 0.7, 0.4

    total = 0.0
    for raw_interest in interests:
        interest = raw_interest.lower().strip()
        if not interest:
            continue

        expanded_terms = INTEREST_SYNONYMS.get(interest, []) + [interest]

        # Take the strongest field where any synonym hits — don't double-count
        # the same interest just because it appears in multiple fields.
        best = 0.0
        for term in expanded_terms:
            if term in title_blob:
                best = max(best, TITLE_W)
            elif term in tags_blob:
                best = max(best, TAGS_W)
            elif term in desc_blob:
                best = max(best, DESC_W)
        total += best

    return min(10.0, (total / len(interests)) * 10.0)

def _proximity_score(value: int | float, preferred: int | float, min_val: float, max_val: float) -> float:
    """
    Return a 0–10 score based on how close `value` is to `preferred`.

    A perfect match gives 10; the maximum possible distance gives 0.
    This lets students say "I want a workload of 2" and courses near 2
    score high while courses near 5 score low, regardless of direction.
    """
    max_distance = max_val - min_val          # e.g. 9 for difficulty, 4 for workload
    distance = abs(value - preferred)
    proximity = 1.0 - (distance / max_distance)   # 1.0 = perfect match, 0.0 = opposite end
    return proximity * 10.0


def _rating_score(rating: float | None) -> float:
    """
    Convert a raw rating (1–5 scale) to a 0–10 score.

    Unlike difficulty and workload, rating is not proximity-based —
    a higher rating is always better regardless of student preference.
    If no rating exists yet, fall back to the neutral mid-point so
    unrated courses aren't unfairly punished.
    """
    raw = rating if rating is not None else RATING_NEUTRAL
    # Normalize from [RATING_MIN, RATING_MAX] → [0, 10]
    return ((raw - RATING_MIN) / (RATING_MAX - RATING_MIN)) * 10.0


def score_course(course: "Course", preferences: dict, interest_score: float | None = None) -> float:
    """
    Score a course from 0.0 to 10.0 (1 decimal place) based on how well
    it matches the student's preferences.

    Expected keys in `preferences`:
        preferred_difficulty (int, 1–10): how hard the student wants courses to be
        preferred_workload   (int, 1–5):  how much weekly effort they want

    Weights:
        difficulty  22.5%  — proximity to preferred difficulty
        workload    22.5%  — proximity to preferred workload
        rating      20%    — normalized course rating (higher is always better)
        interest    35%    — how well the course matches the student's interests

    The optional `interest_score` parameter lets callers inject a pre-computed
    value (e.g. a normalised semantic similarity score from recommend_courses).
    When omitted, the keyword-based _interest_score() is used as a fallback so
    this function remains usable without a pre-built embedding index.
    """
    preferred_difficulty = preferences.get("preferred_difficulty", 5)
    preferred_workload   = preferences.get("preferred_workload", 3)

    diff_score   = _proximity_score(course.difficulty, preferred_difficulty, DIFFICULTY_MIN, DIFFICULTY_MAX)
    work_score   = _proximity_score(course.workload,   preferred_workload,   WORKLOAD_MIN,   WORKLOAD_MAX)
    rating_score = _rating_score(course.rating)

    if interest_score is None:
        interest_score = _interest_score(course, preferences.get("interests", []))

    raw = (
        WEIGHT_DIFFICULTY * diff_score +
        WEIGHT_WORKLOAD   * work_score +
        WEIGHT_RATING     * rating_score +
        INTEREST_WEIGHT   * interest_score
    )

    # Clamp to [0, 10] as a safety net, then round to 1 decimal place.
    return round(max(0.0, min(10.0, raw)), 1)


def recommend_courses(course_list: list["Course"], preferences: dict, top_n: int = 5) -> list[tuple["Course", float]]:
    """
    Return the top courses sorted by score (highest first).

    Uses a two-phase approach:
      1. Semantic pre-filter — for each interest, call semantic_search() to
         get the top 50 embedding-nearest courses. Take the union across all
         interests, keeping the best similarity score per course. This limits
         scoring to the ~50-150 most conceptually relevant candidates instead
         of the entire 3000-course catalog, which prevents keyword false-positives
         (e.g. a history-of-computing course scoring the same as CSC108 because
         both mention the word "computing").
      2. Full scoring — run score_course() on each candidate, injecting the
         normalised semantic similarity as the interest score component. The
         similarity is normalised relative to the top match so the best
         candidate always receives 10/10 and others scale down proportionally.

    WHY normalise relative to the top match rather than using raw cosine similarity:
        Raw cosine values vary by query ("coding" might have a max sim of 0.65
        while "machine learning" peaks at 0.82). Normalising removes this
        query-to-query variance so the interest weight (35%) is consistent
        regardless of how well the embedding space separates a particular topic.

    Args:
        course_list:  the pool of courses to rank (all courses in the DB)
        preferences:  same dict passed to score_course
        top_n:        cap on returned results; None returns all passing min_score
    """
    from embeddings import semantic_search  # local import avoids circular dep at module load

    interests = preferences.get("interests", [])
    completed = preferences.get("completed_courses", [])

    if interests:
        # Query the embedding index once per interest and union the results.
        # top_n=50 per interest gives ample candidate coverage without scoring
        # the full catalog. Courses that match multiple interests keep the best sim.
        code_to_sim: dict[str, float] = {}
        for interest in interests:
            for code, sim in semantic_search(interest, top_n=50):
                code_to_sim[code] = max(code_to_sim.get(code, 0.0), sim)

        # Normalise to [0, 10] so the top semantic match always scores 10/10.
        max_sim = max(code_to_sim.values()) if code_to_sim else 1.0

        code_to_course = {c.get_course_code(): c for c in course_list}
        candidates: list[tuple["Course", float]] = [
            (code_to_course[code], min(10.0, (sim / max_sim) * 10.0))
            for code, sim in code_to_sim.items()
            if code in code_to_course
        ]

        eligible = [
            (course, interest_score)
            for course, interest_score in candidates
            if course.is_eligible(completed)
        ]
    else:
        # No interests provided — fall back to full catalog with interest score = 0.
        # Courses are ranked purely by difficulty/workload/rating proximity.
        eligible = [
            (course, 0.0)
            for course in course_list
            if course.is_eligible(completed)
        ]

    scored = [
        (course, score_course(course, preferences, interest_score))
        for course, interest_score in eligible
    ]

    # Filter out weak matches — a score below 5 implies marginal relevance,
    # which is misleading. If this removes everything, the frontend should show
    # a "no strong matches" message rather than showing low-scoring filler.
    min_score = preferences.get("min_score", 5.0)
    scored = [(c, s) for c, s in scored if s >= min_score]

    scored.sort(key=lambda pair: (-pair[1], pair[0].get_course_code()))
    return scored[:top_n] if top_n is not None else scored


# How far a course's difficulty/workload can be from the student's preference
# before we stop calling it a "match". Keeps explain() language honest —
# we won't say "matches your difficulty preference" if the gap is large.
_DIFFICULTY_MATCH_THRESHOLD = 2   # out of a 1–10 scale
_WORKLOAD_MATCH_THRESHOLD   = 1   # out of a 1–5 scale
_GOOD_RATING_THRESHOLD      = 4.0 # out of 5 — "well rated"


def explain_structured(course: "Course", preferences: dict) -> list[dict]:
    """
    Same logic as explain(), but returns a list of structured reason objects
    instead of a single joined string.

    WHY structured instead of a flat string:
        A plain string forces the frontend to parse meaning back out of English
        prose — fragile and unextendable. Structured reasons let the UI render
        each signal with its own icon, colour, or tooltip without any string splitting.

    Each reason dict has:
        type     (str)  — "difficulty" | "workload" | "rating" | "interest"
                          Lets the frontend pick an icon or colour per category.
        message  (str)  — the same human-readable phrase from explain()
        positive (bool) — True means "this is a green/positive signal",
                          False means "worth noting but cautionary".
                          The frontend uses this to decide chip colour.

    The list is ordered: difficulty → workload → rating → interest,
    matching the order in explain() so both outputs feel consistent.
    """
    reasons: list[dict] = []

    preferred_difficulty = preferences.get("preferred_difficulty", 5)
    preferred_workload   = preferences.get("preferred_workload", 3)

    # --- Difficulty ---
    diff_gap = abs(course.difficulty - preferred_difficulty)
    if diff_gap <= _DIFFICULTY_MATCH_THRESHOLD:
        reasons.append({
            "type": "difficulty",
            "message": "matches your preferred difficulty level",
            "positive": True,
        })
    elif course.difficulty < preferred_difficulty:
        reasons.append({
            "type": "difficulty",
            "message": "lighter than your usual preference (good for a busy semester)",
            "positive": True,
        })
    else:
        reasons.append({
            "type": "difficulty",
            "message": "more challenging than your preference (great if you want a stretch)",
            "positive": False,
        })

    # --- Workload ---
    work_gap = abs(course.workload - preferred_workload)
    if work_gap <= _WORKLOAD_MATCH_THRESHOLD:
        reasons.append({
            "type": "workload",
            "message": "fits your workload preference",
            "positive": True,
        })
    elif course.workload < preferred_workload:
        reasons.append({
            "type": "workload",
            "message": "lower workload than you requested, but can still work",
            "positive": True,
        })
    elif course.workload > preferred_workload and 1 < work_gap <= 2:
        reasons.append({
            "type": "workload",
            "message": "heavier workload than you requested, but still manageable",
            "positive": False,
        })
    else:
        reasons.append({
            "type": "workload",
            "message": "a lot heavier than you requested",
            "positive": False,
        })

    # --- Rating ---
    # Same silence rule as explain(): only surface rating when it's notable.
    if course.rating is not None:
        if course.rating >= _GOOD_RATING_THRESHOLD:
            reasons.append({
                "type": "rating",
                "message": f"well rated by students ({course.rating}/5)",
                "positive": True,
            })
        elif course.rating < 3.0:
            reasons.append({
                "type": "rating",
                "message": f"lower student rating ({course.rating}/5) — worth considering",
                "positive": False,
            })

    # --- Interest match ---
    interests = preferences.get("interests", [])
    if interests:
        searchable = " ".join(course.tags + [course.description, course.get_name()]).lower()
        matched_interests = [
            i for i in interests
            if any(t in searchable for t in INTEREST_SYNONYMS.get(i.lower().strip(), []) + [i.lower().strip()])
        ]
        if matched_interests:
            reasons.append({
                "type": "interest",
                "message": f"aligns with your interest in {', '.join(matched_interests)}",
                "positive": True,
            })
        else:
            reasons.append({
                "type": "interest",
                "message": "does not directly match your stated interests — consider as a breadth requirement",
                "positive": False,
            })

    return reasons


def explain(course: "Course", preferences: dict) -> str:
    """
    Generate a plain-English explanation of why a course was recommended.

    This is rule-based for now (fast, transparent, no AI cost). Each rule
    appends a short phrase; the phrases are joined into one readable sentence.
    When we add interest tags and major-fit signals later, new rules slot in
    here without touching the scoring logic.

    Returns an empty string if nothing notable matches — callers should handle
    that gracefully (e.g. "No specific reasons found.").
    """
    reasons = []

    preferred_difficulty = preferences.get("preferred_difficulty", 5)
    preferred_workload   = preferences.get("preferred_workload", 3)

    # --- Difficulty ---
    diff_gap = abs(course.difficulty - preferred_difficulty)
    if diff_gap <= _DIFFICULTY_MATCH_THRESHOLD:
        reasons.append("matches your preferred difficulty level")
    elif course.difficulty < preferred_difficulty:
        # Student wants harder courses; this one is lighter — still useful to flag.
        reasons.append("lighter than your usual preference (good for a busy semester)")
    else:
        reasons.append("more challenging than your preference (great if you want a stretch)")

    # --- Workload ---
    work_gap = abs(course.workload - preferred_workload)
    if work_gap <= _WORKLOAD_MATCH_THRESHOLD:
        reasons.append("fits your workload preference")
    elif course.workload < preferred_workload:
        reasons.append("lower workload than you requested")
    else:
        reasons.append("heavier workload than you requested")

    # --- Rating ---
    # Only mention rating when it exists and is actually notable; silence is
    # better than "no rating yet" cluttering every explanation.
    if course.rating is not None:
        if course.rating >= _GOOD_RATING_THRESHOLD:
            reasons.append(f"well rated by students ({course.rating}/5)")
        elif course.rating < 3.0:
            reasons.append(f"lower student rating ({course.rating}/5) — worth considering")

    # --- Interest match ---
    # Tell the student *why* this course appeared — or warn them if it's a
    # weak interest match so they know to look closer before enrolling.
    interests = preferences.get("interests", [])
    if interests:
        # Reuse the same expanded-term logic from _interest_score so the
        # explanation is always consistent with the actual score.
        searchable = " ".join(course.tags + [course.description, course.get_name()]).lower()
        matched_interests = [
            i for i in interests
            if any(t in searchable for t in INTEREST_SYNONYMS.get(i.lower().strip(), []) + [i.lower().strip()])
        ]
        if matched_interests:
            reasons.append(f"aligns with your interest in {', '.join(matched_interests)}")
        else:
            reasons.append("does not directly match your stated interests — consider as a breadth requirement")

    return ", ".join(reasons) if reasons else "No specific reasons found."

def _extract_interests_from_text(text: str) -> list[str]:
    """
    Pull interest keywords out of free text by matching against INTEREST_SYNONYMS.

    Two passes so multi-word phrases like "machine learning" are caught before
    their component words ("machine", "learning") are checked individually.
    Once a phrase is matched it's blanked out so the single-word pass doesn't
    double-count the same concept.

    Returns deduplicated list in first-seen order.
    """
    text_lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()

    # Full vocabulary: keys of the map plus every synonym value
    # WHY include values: a student might type "programming" directly, which is a
    # synonym value but not a key — we still want to treat it as a known interest.
    all_known: set[str] = set(INTEREST_SYNONYMS.keys())
    for synonyms in INTEREST_SYNONYMS.values():
        all_known.update(synonyms)

    # Pass 1: longest multi-word phrases first so "machine learning" wins over "machine"
    multi_word = sorted((t for t in all_known if " " in t), key=len, reverse=True)
    for phrase in multi_word:
        if phrase in text_lower and phrase not in seen:
            found.append(phrase)
            seen.add(phrase)
            text_lower = text_lower.replace(phrase, " ")

    # Pass 2: remaining single words — use regex to strip punctuation before matching
    for word in re.findall(r"[a-z]+", text_lower):
        if word in all_known and word not in seen:
            found.append(word)
            seen.add(word)

    return found


# Matches UofT course codes with or without the suffix: MAT148, MAT148H1, CSC108H5S, ECO101Y1
_COURSE_CODE_RE = re.compile(r'\b([A-Z]{2,4}\d{3}[HY]?\d?)\b', re.IGNORECASE)

# Words that carry no semantic signal for course retrieval. Stripping these before
# embedding prevents conversational phrasing ("Do you have any coding courses to
# recommend to a first year") from pulling the query vector toward generic filler
# and away from the meaningful terms ("coding", "first year").
# WHY a frozenset: O(1) membership test; we check every token so speed matters.
_STOP_WORDS: frozenset[str] = frozenset({
    # question/conversational openers
    "do", "does", "did", "can", "could", "would", "should", "will", "shall",
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had",
    # pronouns
    "i", "me", "my", "we", "you", "your", "it", "its",
    # articles / determiners
    "a", "an", "the", "any", "some", "no", "all",
    # prepositions / conjunctions
    "to", "for", "of", "in", "on", "at", "by", "from", "with", "about",
    "and", "or", "but", "so", "if", "as",
    # filler verbs & adverbs in course queries
    "want", "need", "like", "know", "think", "tell", "show", "give",
    "recommend", "suggest", "find", "get", "take",
    "please", "just", "really", "very", "more", "also",
    # question words (after stripping these the nouns/topics remain)
    "what", "which", "who", "where", "when", "how", "why",
    # other high-frequency noise
    "there", "here", "this", "that", "these", "those",
    "up", "out", "into", "than", "then", "now",
})


def _strip_filler(text: str) -> str:
    """
    Remove stop words from a free-text query before embedding.

    Keeps only tokens that carry subject-matter signal so the embedding
    vector reflects the student's actual topic intent rather than conversational
    framing. Preserves the relative order of meaningful tokens.

    Example:
        "Do you have any coding courses to recommend to a first year"
        → "coding courses first year"
    """
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    meaningful = [t for t in tokens if t not in _STOP_WORDS]
    # Fall back to the original text if stripping removes everything
    # (e.g. a one-word stop word query — rare but safe to handle).
    return " ".join(meaningful) if meaningful else text


def _find_courses_by_code(message: str, course_list: list["Course"]) -> list[tuple["Course", float]]:
    """
    Direct course-code lookup before any interest scoring runs.

    WHY this exists: interest extraction strips digits (re.findall(r"[a-z]+"...))
    so "MAT148" becomes just "mat", which substring-matches hundreds of unrelated
    courses ("cli-mat-e", "mat-hematics"). This step catches course-code patterns
    first and pins matched courses at max score so they always appear in the top N.
    """
    found: list[tuple["Course", float]] = []
    seen_codes: set[str] = set()
    for m in _COURSE_CODE_RE.finditer(message):
        query = m.group(1).upper()
        for course in course_list:
            code = course.get_course_code().upper()
            # startswith so "MAT148" matches "MAT148H1", "MAT148H5", etc.
            if code.startswith(query) and code not in seen_codes:
                found.append((course, 10.0))
                seen_codes.add(code)
    return found


def search_by_message(message: str, course_list: list["Course"], top_n: int = 5) -> list[tuple["Course", float]]:
    """
    Find the most relevant courses for a free-text message.

    Two-pass retrieval:
      1. Course-code detection — if the message contains a UofT code pattern
         (e.g. "MAT148", "CSC108H1") those courses are pinned at the top with
         a score of 10.0. This is exact-match, always wins over semantic.
      2. Semantic search — encode the query and rank all remaining courses by
         cosine similarity against the pre-built embedding index. This handles
         natural language like "proof-based math course" or "machine learning
         for non-CS students" that keyword matching would miss or mangle.

    WHY replace keyword scoring here:
        _interest_score() was designed for the /recommend flow where the student
        explicitly states interests. For freeform chat messages it degrades badly
        because (a) digits are stripped so "MAT148" → "mat" → 100+ false matches,
        and (b) the synonym map can't cover every subject a student might mention.
        Semantic similarity handles both cases without a manually curated map.

    Note: _extract_interests_from_text(), _interest_score(), and INTEREST_SYNONYMS
    are still used by score_course() / explain() for the /recommend endpoint.
    Only this function is switching to semantic retrieval.
    """
    from embeddings import semantic_search  # local import avoids circular dependency at module load

    # Pass 1: exact course-code lookup — highest priority, no semantic needed
    code_hits = _find_courses_by_code(message, course_list)
    code_hit_codes = {c.get_course_code() for c, _ in code_hits}

    # Pass 2: semantic search fills the remaining slots
    remaining = top_n - len(code_hits)
    semantic_hits: list[tuple["Course", float]] = []
    if remaining > 0:
        # Strip conversational filler before embedding so the query vector reflects
        # topic intent rather than phrasing. "Do you have any coding courses to
        # recommend to a first year" → "coding courses first year".
        semantic_query = _strip_filler(message)

        # O(1) code → Course lookup so we can resolve codes returned by semantic_search()
        code_to_course = {c.get_course_code(): c for c in course_list}
        # Request more than we need so we have enough candidates after filtering
        for code, score in semantic_search(semantic_query, top_n=top_n + len(code_hits)):
            if code not in code_hit_codes and code in code_to_course:
                semantic_hits.append((code_to_course[code], score))
                if len(semantic_hits) >= remaining:
                    break

    return code_hits + semantic_hits