from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

# Lazy singleton — model is ~90 MB and takes a few seconds to load.
# We load it once on first call and reuse it for the lifetime of the process.
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # all-MiniLM-L6-v2: 384-dim vectors, fast, good quality for semantic search.
        # Hugging Face caches the download to ~/.cache/huggingface after the first run.
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def encode(texts: list[str]) -> np.ndarray:
    """Embed a list of strings. Returns shape (len(texts), 384)."""
    return get_model().encode(texts, show_progress_bar=True, convert_to_numpy=True)
