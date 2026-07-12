"""
Tests for embeddings.py's Voyage AI-backed encode/search functions.

Mocks voyageai.Client.embed (the actual network boundary) rather than our
own encode()/semantic_search() wrappers, so these tests exercise our real
conversion/ranking logic against a stubbed API response.
"""
from unittest.mock import patch

import numpy as np
import voyageai

import embeddings


def _stub_embeddings(vectors: list[list[float]]) -> voyageai.object.embeddings.EmbeddingsObject:
    obj = voyageai.object.embeddings.EmbeddingsObject()
    obj.embeddings = vectors
    obj.total_tokens = 0
    return obj


def test_encode_converts_voyage_response_to_numpy_array():
    with patch.object(
        voyageai.Client, "embed", return_value=_stub_embeddings([[0.1, 0.2, 0.3]])
    ):
        result = embeddings.encode(["some course text"])

    assert isinstance(result, np.ndarray)
    assert np.allclose(result, [[0.1, 0.2, 0.3]])


def test_encode_batches_requests_over_voyages_1000_text_limit():
    # Voyage's API hard-caps a single request at 1000 texts (confirmed against
    # the real API: re-embedding the ~3200-course catalog in one call fails
    # with InvalidRequestError). encode() must split into <=1000-text chunks
    # and stitch the results back together in the original order.
    texts = [f"text-{i}" for i in range(1500)]

    def fake_embed(batch, model=None, input_type=None, **kwargs):
        assert len(batch) <= 1000
        return _stub_embeddings([[int(t.split("-")[1])] for t in batch])

    with patch.object(voyageai.Client, "embed", side_effect=fake_embed):
        result = embeddings.encode(texts)

    assert result.shape == (1500, 1)
    assert result.flatten().tolist() == list(range(1500))


def test_semantic_search_ranks_by_similarity_to_mocked_query_embedding(monkeypatch):
    # Three course vectors along the x/y/z axes — a query aligned with one
    # axis should rank that course first by cosine similarity.
    test_vectors = np.array([
        [1.0, 0.0, 0.0],  # CSC108H1
        [0.0, 1.0, 0.0],  # MAT137H1
        [0.0, 0.0, 1.0],  # PHY131H1
    ])
    test_codes = ["CSC108H1", "MAT137H1", "PHY131H1"]
    monkeypatch.setattr(embeddings, "_load_index", lambda: (test_vectors, test_codes))
    monkeypatch.setattr(embeddings, "_vectors", None)
    monkeypatch.setattr(embeddings, "_codes", None)

    with patch.object(
        voyageai.Client, "embed", return_value=_stub_embeddings([[0.0, 1.0, 0.0]])
    ):
        results = embeddings.semantic_search("linear algebra", top_n=3)

    # MAT137H1 is an exact match (cosine sim 1.0); the other two axes are
    # orthogonal to the query so they tie at 0.0 — only the top result is
    # deterministic here.
    assert results[0][0] == "MAT137H1"
    assert results[0][1] > results[1][1]


def test_semantic_search_masks_out_disallowed_codes(monkeypatch):
    test_vectors = np.array([
        [1.0, 0.0, 0.0],  # CSC108H1
        [0.0, 1.0, 0.0],  # MAT137H1
    ])
    test_codes = ["CSC108H1", "MAT137H1"]
    monkeypatch.setattr(embeddings, "_load_index", lambda: (test_vectors, test_codes))
    monkeypatch.setattr(embeddings, "_vectors", None)
    monkeypatch.setattr(embeddings, "_codes", None)

    with patch.object(
        voyageai.Client, "embed", return_value=_stub_embeddings([[0.0, 1.0, 0.0]])
    ):
        results = embeddings.semantic_search(
            "linear algebra", top_n=3, allowed_codes={"CSC108H1"}
        )

    assert [code for code, _ in results] == ["CSC108H1"]


def test_program_semantic_search_ranks_by_similarity_to_mocked_query_embedding(monkeypatch):
    test_vectors = np.array([
        [1.0, 0.0],  # Computer Science Specialist
        [0.0, 1.0],  # English Major
    ])
    test_codes = ["ASSPE1689", "ASMAJ0161"]
    monkeypatch.setattr(embeddings, "_load_program_index", lambda: (test_vectors, test_codes))
    monkeypatch.setattr(embeddings, "_program_vectors", None)
    monkeypatch.setattr(embeddings, "_program_codes", None)

    with patch.object(
        voyageai.Client, "embed", return_value=_stub_embeddings([[1.0, 0.0]])
    ):
        results = embeddings.program_semantic_search("computer science", top_n=2)

    assert results[0][0] == "ASSPE1689"


def test_program_semantic_search_masks_out_disallowed_codes(monkeypatch):
    # Mirrors test_semantic_search_masks_out_disallowed_codes above: masked-out
    # (-inf similarity) programs must be dropped, not just sorted last — a
    # narrow allowed_codes filter should return a short list, not backfill
    # with excluded programs to satisfy top_n.
    test_vectors = np.array([
        [1.0, 0.0],  # Computer Science Specialist
        [0.0, 1.0],  # English Major
    ])
    test_codes = ["ASSPE1689", "ASMAJ0161"]
    monkeypatch.setattr(embeddings, "_load_program_index", lambda: (test_vectors, test_codes))
    monkeypatch.setattr(embeddings, "_program_vectors", None)
    monkeypatch.setattr(embeddings, "_program_codes", None)

    with patch.object(
        voyageai.Client, "embed", return_value=_stub_embeddings([[1.0, 0.0]])
    ):
        results = embeddings.program_semantic_search(
            "computer science", top_n=2, allowed_codes={"ASSPE1689"}
        )

    assert [code for code, _ in results] == ["ASSPE1689"]
