from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import voyageai

# ── Client singleton ─────────────────────────────────────────────────────────
# Voyage API calls replace the local sentence-transformers model — that model
# kept ~90MB of weights plus torch's much larger runtime overhead resident in
# memory for the process lifetime, which was the dominant driver of Railway's
# RAM-based billing. voyageai.Client() picks up VOYAGE_API_KEY from the
# environment when no key is passed explicitly.
_client: voyageai.Client | None = None

_MODEL = "voyage-3-lite"

# Voyage hard-caps a single embed() request at 1000 texts — confirmed against
# the real API when re-embedding the ~3200-course catalog in one call.
_MAX_BATCH_SIZE = 1000


def get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client()
    return _client


def encode(texts: list[str], input_type: str | None = None) -> np.ndarray:
    """
    Embed a list of strings via the Voyage API. Returns shape (len(texts), dim).

    input_type ("query" or "document") tells Voyage which side of a retrieval
    pair this text is — its models are trained asymmetrically, so tagging each
    side improves ranking quality over embedding both sides identically.

    Splits into <=1000-text requests since that's Voyage's hard per-request
    limit; single queries (the common runtime case) never hit this path.
    """
    client = get_client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _MAX_BATCH_SIZE):
        batch = texts[i:i + _MAX_BATCH_SIZE]
        result = client.embed(batch, model=_MODEL, input_type=input_type)
        all_embeddings.extend(result.embeddings)
    return np.array(all_embeddings)


# ── Embedding index singleton ────────────────────────────────────────────────
# Loaded lazily from disk on first semantic_search() call. The .npy matrix is
# ~5 MB so we keep it in memory for the lifetime of the process rather than
# re-reading it on each request.
_vectors: np.ndarray | None = None
_codes: list[str] | None = None


def _load_index() -> tuple[np.ndarray, list[str]]:
    global _vectors, _codes
    if _vectors is None:
        here = Path(__file__).parent
        _vectors = np.load(here / "course_embeddings.npy")
        with open(here / "course_codes.json", encoding="utf-8") as f:
            _codes = json.load(f)
    return _vectors, _codes


def semantic_search(
    query: str,
    top_n: int = 5,
    allowed_codes: set[str] | None = None,
) -> list[tuple[str, float]]:
    """
    Find the top_n most semantically similar courses for a free-text query.

    Returns (course_code, cosine_similarity) pairs sorted highest-first.

    Args:
        query:         Free-text search string (stop-word-stripped recommended).
        top_n:         Maximum number of results to return.
        allowed_codes: When provided, only these course codes can be returned;
                       everything else is masked out before the top-N pick.
                       Filtering here (not after the search) guarantees we still
                       return a full top_n even when many courses are excluded.

    Uses cosine similarity, not a raw dot product, because the stored vectors
    aren't normalised — a plain dot product would just reward courses with
    longer descriptions instead of ones that actually match.
    """
    vectors, codes = _load_index()
    query_vec = encode([query], input_type="query")[0]

    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    # Guard against zero-magnitude vectors (shouldn't happen, but safe)
    sims = (vectors @ query_vec) / np.where(norms == 0, 1e-9, norms)

    if allowed_codes is not None:
        # Mask excluded rows to -inf so they can never win a top-N slot. We use
        # -inf rather than 0 because cosine scores live in [-1, 1], so any finite
        # sentinel could collide with a real score.
        mask = np.array([c in allowed_codes for c in codes], dtype=bool)
        sims = np.where(mask, sims, -np.inf)

    # Drop masked-out (-inf) entries entirely rather than just sorting them
    # last — otherwise a narrow allowed_codes filter (fewer real candidates
    # than top_n) would backfill the result with excluded courses instead of
    # returning a short, fully-valid list.
    order = np.argsort(sims)[::-1]
    top_indices = [i for i in order if sims[i] != -np.inf][:top_n]
    return [(codes[i], float(sims[i])) for i in top_indices]


# ── Program embedding index singleton ────────────────────────────────────────
# Separate vector matrices from the course index, but the same _model singleton.
# Kept apart so program search and course search don't share a vector space.
_program_vectors: np.ndarray | None = None
_program_codes: list[str] | None = None


def _load_program_index() -> tuple[np.ndarray, list[str]]:
    """Load program embeddings from disk, caching in module-level globals."""
    global _program_vectors, _program_codes
    if _program_vectors is None:
        here = Path(__file__).parent
        _program_vectors = np.load(here / "program_embeddings.npy")
        with open(here / "program_codes.json", encoding="utf-8") as f:
            _program_codes = json.load(f)
    return _program_vectors, _program_codes


def program_semantic_search(
    query: str,
    top_n: int = 3,
    allowed_codes: set[str] | None = None,
) -> list[tuple[str, float]]:
    """
    Find the top_n most semantically similar programs for a free-text query.

    Same cosine-similarity approach as semantic_search(), just over the program
    vectors. allowed_codes restricts results to certain program types (e.g. only
    "Specialist"), masking everything else out before the top-N pick.

    This deliberately duplicates semantic_search() instead of sharing logic —
    that function is already stable and reused, so a parallel copy avoids
    touching it and risking existing callers. Could be unified later.
    """
    vectors, codes = _load_program_index()
    query_vec = encode([query], input_type="query")[0]

    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    sims = (vectors @ query_vec) / np.where(norms == 0, 1e-9, norms)

    if allowed_codes is not None:
        mask = np.array([c in allowed_codes for c in codes], dtype=bool)
        sims = np.where(mask, sims, -np.inf)

    order = np.argsort(sims)[::-1]
    top_indices = [i for i in order if sims[i] != -np.inf][:top_n]
    return [(codes[i], float(sims[i])) for i in top_indices]
