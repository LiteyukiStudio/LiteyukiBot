"""Experimental local-document RAG with replaceable provider boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    """Define the structural interface required from a embedding provider."""
    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Implement the embed operation for the embedding provider.

        Args:
            texts: The texts value used by the operation.

        Returns:
            The `Sequence[Sequence[float]]` result produced by the operation.
        """
        ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Represent the retrieved chunk contract."""
    source_id: str
    chunk_id: int
    text: str
    score: float


class Reranker(Protocol):
    """Define the structural interface required from a reranker."""
    def rerank(self, query: str, candidates: Sequence[RetrievedChunk]) -> Sequence[RetrievedChunk]:
        """Implement the rerank operation for the reranker.

        Args:
            query: The query value used by the operation.
            candidates: The candidates value used by the operation.

        Returns:
            The `Sequence[RetrievedChunk]` result produced by the operation.
        """
        ...


class IdentityReranker:
    """Reference reranker that preserves deterministic cosine order."""

    def rerank(self, _query: str, candidates: Sequence[RetrievedChunk]) -> Sequence[RetrievedChunk]:
        """Implement the rerank operation for the identity reranker.

        Args:
            _query: The query value used by the operation.
            candidates: The candidates value used by the operation.

        Returns:
            The `Sequence[RetrievedChunk]` result produced by the operation.
        """
        return candidates


@dataclass(frozen=True, slots=True)
class RagContext:
    """Represent the rag context contract."""
    text: str
    citations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagSettings:
    """Represent the validated rag settings contract."""
    roots: tuple[Path, ...]
    index_path: Path
    chunk_size: int
    chunk_overlap: int
    top_k: int
    context_chars: int
    embedding_model: str
    embedding_api_key: str
    embedding_base_url: str | None
    timeout_seconds: float
    citations: bool

    @classmethod
    def from_options(cls, options: Mapping[str, Any], *, default_directory: Path) -> RagSettings | None:
        """Create the rag settings from options.

        Args:
            options: Validated optional settings for the operation.
            default_directory: The default directory value used by the operation.

        Returns:
            The `RagSettings | None` result produced by the operation.
        """
        raw_roots = options.get("rag_paths", ())
        if not isinstance(raw_roots, Sequence) or isinstance(raw_roots, (str, bytes)):
            raise ValueError("rag_paths must be an array of directories")
        roots = tuple(_path(item, "rag_paths") for item in raw_roots)
        if not roots:
            return None
        chunk_size = _bounded_int(options.get("rag_chunk_size", 512), "rag_chunk_size", 64, 16_384)
        chunk_overlap = _bounded_int(options.get("rag_chunk_overlap", 64), "rag_chunk_overlap", 0, chunk_size - 1)
        top_k = _bounded_int(options.get("rag_top_k", 4), "rag_top_k", 1, 64)
        context_chars = _bounded_int(options.get("rag_context_chars", 8_192), "rag_context_chars", 256, 1_000_000)
        model = _text(options.get("rag_embedding_model", "text-embedding-3-small"), "rag_embedding_model")
        api_key = _text(options.get("rag_embedding_api_key", options.get("api_key")), "rag_embedding_api_key")
        base_url = options.get("rag_embedding_base_url", options.get("base_url"))
        if base_url is not None:
            base_url = _text(base_url, "rag_embedding_base_url")
        index_path = _path(
            options.get("rag_index_path", str(default_directory / "rag.sqlite3")),
            "rag_index_path",
        )
        timeout = _bounded_float(options.get("rag_timeout_seconds", 60.0), "rag_timeout_seconds", 0.1, 3_600.0)
        citations = options.get("rag_citations", False)
        if not isinstance(citations, bool):
            raise ValueError("rag_citations must be boolean")
        for root in roots:
            if not root.is_dir():
                raise ValueError(f"RAG document directory does not exist: {root}")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            roots=roots,
            index_path=index_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
            context_chars=context_chars,
            embedding_model=model,
            embedding_api_key=api_key,
            embedding_base_url=base_url,
            timeout_seconds=timeout,
            citations=citations,
        )


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embedding adapter kept behind the replaceable protocol."""

    def __init__(self, *, api_key: str, base_url: str | None, model: str) -> None:
        """Initialize the open a i embedding provider.

        Args:
            api_key: The api key value used by the operation.
            base_url: The base url value used by the operation.
            model: The model value used by the operation.

        Returns:
            None.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Implement the embed operation for the open a i embedding provider.

        Args:
            texts: The texts value used by the operation.

        Returns:
            The `Sequence[Sequence[float]]` result produced by the operation.
        """
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as error:
            raise RuntimeError("RAG embeddings require the openai package") from error
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            response: Any = await client.embeddings.create(model=self.model, input=list(texts))
        except Exception as error:
            raise RuntimeError("RAG embedding request failed") from error
        return tuple(tuple(float(item) for item in record.embedding) for record in response.data)


class RagIndex:
    """Incremental UTF-8 document index with deterministic local retrieval."""

    def __init__(
        self,
        settings: RagSettings,
        provider: EmbeddingProvider,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        """Initialize the rag index.

        Args:
            settings: Validated application settings.
            provider: The provider value used by the operation.
            reranker: The reranker value used by the operation.

        Returns:
            None.
        """
        self.settings = settings
        self.provider = provider
        self.reranker = reranker or IdentityReranker()
        self._connection = sqlite3.connect(settings.index_path, check_same_thread=False)
        self._connection_lock = threading.RLock()
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                source_id TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                source_id TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                PRIMARY KEY (source_id, chunk_id),
                FOREIGN KEY (source_id) REFERENCES documents(source_id) ON DELETE CASCADE
            )
            """
        )
        self._connection.commit()

    async def sync(self) -> tuple[str, ...]:
        """Implement the sync operation for the rag index.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        seen: set[str] = set()
        seen_paths: set[Path] = set()
        diagnostics: list[str] = []
        for root_index, root in enumerate(self.settings.roots):
            root_id = f"root-{root_index}"
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                normalized_path = path.resolve()
                if normalized_path in seen_paths:
                    continue
                seen_paths.add(normalized_path)
                relative = path.relative_to(root).as_posix()
                source_id = f"{root_id}/{relative}"
                seen.add(source_id)
                try:
                    raw = path.read_bytes()
                    text = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    diagnostics.append(source_id)
                    continue
                content_hash = hashlib.sha256(raw).hexdigest()
                with self._connection_lock:
                    existing = self._connection.execute(
                        "SELECT content_hash FROM documents WHERE source_id = ?", (source_id,)
                    ).fetchone()
                if existing is not None and existing[0] == content_hash:
                    continue
                chunks = _chunks(text, self.settings.chunk_size, self.settings.chunk_overlap)
                if not chunks:
                    chunks = ("",)
                try:
                    embeddings = await asyncio.wait_for(
                        self.provider.embed(chunks), timeout=self.settings.timeout_seconds
                    )
                    vectors = _validate_embeddings(embeddings, len(chunks))
                except (TimeoutError, ValueError, RuntimeError):
                    diagnostics.append(source_id)
                    continue
                with self._connection_lock:
                    self._connection.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
                    self._connection.execute(
                        "INSERT OR REPLACE INTO documents(source_id, content_hash) VALUES (?, ?)",
                        (source_id, content_hash),
                    )
                    self._connection.executemany(
                        "INSERT INTO chunks(source_id, chunk_id, text, embedding) VALUES (?, ?, ?, ?)",
                        (
                            (source_id, index, chunk, json.dumps(vector, separators=(",", ":")))
                            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                        ),
                    )
        with self._connection_lock:
            current = tuple(row[0] for row in self._connection.execute("SELECT source_id FROM documents"))
            for source_id in set(current) - seen:
                self._connection.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
                self._connection.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
            self._connection.commit()
        return tuple(sorted(diagnostics))

    async def retrieve(self, query: str) -> RagContext:
        """Implement the retrieve operation for the rag index.

        Args:
            query: The query value used by the operation.

        Returns:
            The `RagContext` result produced by the operation.
        """
        if not query.strip():
            return RagContext("")
        embeddings = await asyncio.wait_for(self.provider.embed((query,)), timeout=self.settings.timeout_seconds)
        query_vector = _validate_embeddings(embeddings, 1)[0]
        candidates = await asyncio.to_thread(self._score_candidates, query_vector)
        ranked = tuple(self.reranker.rerank(query, candidates[: self.settings.top_k * 4]))[: self.settings.top_k]
        selected: list[RetrievedChunk] = []
        remaining = self.settings.context_chars
        for candidate in ranked:
            rendered = f"[{candidate.source_id}#{candidate.chunk_id}] {candidate.text}"
            if len(rendered) > remaining:
                break
            selected.append(candidate)
            remaining -= len(rendered) + 1
        text = "\n".join(f"[{item.source_id}#{item.chunk_id}] {item.text}" for item in selected)
        citations = tuple(f"{item.source_id}#{item.chunk_id}" for item in selected) if self.settings.citations else ()
        return RagContext(text=text, citations=citations)

    def close(self) -> None:
        """Close the rag index and release its owned resources.

        Returns:
            None.
        """
        with self._connection_lock:
            self._connection.close()

    def _score_candidates(self, query_vector: Sequence[float]) -> tuple[RetrievedChunk, ...]:
        """Implement the score candidates operation for the rag index.

        Args:
            query_vector: The query vector value used by the operation.

        Returns:
            The `tuple[RetrievedChunk, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `RagIndex._score_candidates`. It delegates to `execute`,
            `int`, `_cosine`, `float` while keeping intermediate state local to the owning operation.
        """
        with self._connection_lock:
            rows = tuple(self._connection.execute("SELECT source_id, chunk_id, text, embedding FROM chunks"))
        candidates = [
            RetrievedChunk(
                source_id=str(source_id),
                chunk_id=int(chunk_id),
                text=str(text),
                score=_cosine(query_vector, tuple(float(item) for item in json.loads(raw_embedding))),
            )
            for source_id, chunk_id, text, raw_embedding in rows
        ]
        candidates.sort(key=lambda item: (-item.score, item.source_id, item.chunk_id))
        return tuple(candidates)


def _chunks(text: str, size: int, overlap: int) -> tuple[str, ...]:
    """Implement the chunks operation for the component.

    Args:
        text: The text value used by the operation.
        size: The size value used by the operation.
        overlap: The overlap value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_chunks`. It delegates to `range` while keeping intermediate
        state local to the owning operation.
    """
    if not text:
        return ()
    step = size - overlap
    return tuple(text[index : index + size] for index in range(0, len(text), step))


def _validate_embeddings(values: Sequence[Sequence[float]], expected: int) -> tuple[tuple[float, ...], ...]:
    """Validate embeddings.

    Args:
        values: The values value used by the operation.
        expected: The expected value used by the operation.

    Returns:
        The `tuple[tuple[float, ...], ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_embeddings`. It delegates to `float`, `any`,
        `isfinite` while keeping intermediate state local to the owning operation.
    """
    if len(values) != expected or not values:
        raise ValueError("embedding provider returned an unexpected item count")
    vectors = tuple(tuple(float(item) for item in value) for value in values)
    dimension = len(vectors[0])
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise ValueError("embedding provider returned inconsistent dimensions")
    if any(not math.isfinite(item) for vector in vectors for item in vector):
        raise ValueError("embedding provider returned non-finite values")
    return vectors


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Implement the cosine operation for the component.

    Args:
        left: The left value used by the operation.
        right: The right value used by the operation.

    Returns:
        The `float` result produced by the operation.

    Notes:
        Internal implementation detail for `_cosine`. It delegates to `sqrt`, `sum`, `zip` while keeping
        intermediate state local to the owning operation.
    """
    if len(left) != len(right):
        return -1.0
    denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(sum(item * item for item in right))
    return 0.0 if denominator == 0 else sum(a * b for a, b in zip(left, right, strict=True)) / denominator


def _path(value: object, field: str) -> Path:
    """Implement the path operation for the component.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.

    Returns:
        The `Path` result produced by the operation.

    Notes:
        Internal implementation detail for `_path`. It delegates to `strip`, `resolve` while keeping
        intermediate state local to the owning operation.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    return Path(value).resolve()


def _text(value: object, field: str) -> str:
    """Implement the text operation for the component.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_text`. It delegates to `strip` while keeping intermediate
        state local to the owning operation.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    """Implement the bounded int operation for the component.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.
        minimum: The minimum value used by the operation.
        maximum: The maximum value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_bounded_int`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def _bounded_float(value: object, field: str, minimum: float, maximum: float) -> float:
    """Implement the bounded float operation for the component.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.
        minimum: The minimum value used by the operation.
        maximum: The maximum value used by the operation.

    Returns:
        The `float` result produced by the operation.

    Notes:
        Internal implementation detail for `_bounded_float`. It delegates to `float` while keeping
        intermediate state local to the owning operation.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return float(value)


__all__ = [
    "EmbeddingProvider",
    "IdentityReranker",
    "OpenAIEmbeddingProvider",
    "RagContext",
    "RagIndex",
    "RagSettings",
    "Reranker",
    "RetrievedChunk",
]
