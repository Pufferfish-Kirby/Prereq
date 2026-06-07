from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# ── Model singleton ──────────────────────────────────────────────────────────
# ~90 MB, takes a few seconds to load. Loaded once on first encode/search call.
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def encode(texts: list[str], show_progress: bool = False) -> np.ndarray:
    """Embed a list of strings. Returns shape (len(texts), 384)."""
    return get_model().encode(texts, show_progress_bar=show_progress, convert_to_numpy=True)


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


def semantic_search(query: str, top_n: int = 5) -> list[tuple[str, float]]:
    """
    Find the top_n most semantically similar courses for a free-text query.

    Returns (course_code, cosine_similarity) pairs sorted highest-first.

    WHY cosine similarity over dot product:
        The stored vectors are not L2-normalised, so raw dot products would
        favour longer (higher-magnitude) vectors. Cosine similarity normalises
        both sides so we measure angle, not magnitude — a course with a very
        long description won't automatically beat a short one.
    """
    vectors, codes = _load_index()
    query_vec = get_model().encode([query], convert_to_numpy=True)[0]  # (384,)

    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    # Guard against zero-magnitude vectors (shouldn't happen, but safe)
    sims = (vectors @ query_vec) / np.where(norms == 0, 1e-9, norms)

    top_indices = np.argsort(sims)[::-1][:top_n]
    return [(codes[i], float(sims[i])) for i in top_indices]
