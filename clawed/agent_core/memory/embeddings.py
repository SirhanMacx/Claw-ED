"""Embedding providers for semantic search.

Priority:
1. ONNX MiniLM (if onnxruntime + tokenizers installed — best quality, offline)
2. Ollama embeddings (if local Ollama running with embedding model)
3. TF-IDF with bigrams (no dependencies, always works — poor quality)

The ONNX embedder auto-downloads all-MiniLM-L6-v2 (~22MB) on first use.
Produces 384-dimensional dense vectors — compact, fast, high quality.
"""
from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(
    os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
) / "models" / "minilm"

_MODEL_URL = (
    "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/"
    "resolve/main/onnx/model.onnx"
)
_TOKENIZER_URL = (
    "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/"
    "resolve/main/tokenizer.json"
)


# ── ONNX MiniLM Embedder ────────────────────────────────────────────


class ONNXMiniLMEmbedder:
    """all-MiniLM-L6-v2 via ONNX Runtime — 384-dim dense vectors.

    Auto-downloads model (~22MB) and tokenizer on first use.
    Requires: onnxruntime, tokenizers, numpy.
    """

    _DIM = 384

    def __init__(self, model_dir: Path | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._session: Any = None
        self._tokenizer: Any = None
        self._ready = False

    def _ensure_model(self) -> bool:
        """Download model and tokenizer if not cached."""
        if self._ready:
            return True

        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"

        self._model_dir.mkdir(parents=True, exist_ok=True)

        # Download if missing
        for url, path in [
            (_MODEL_URL, model_path),
            (_TOKENIZER_URL, tokenizer_path),
        ]:
            if not path.exists() or path.stat().st_size < 1000:
                logger.info("Downloading %s → %s", url.split("/")[-1], path)
                downloaded = False
                for attempt in range(3):
                    try:
                        import httpx
                        with httpx.Client(
                            timeout=120,
                            follow_redirects=True,
                            http2=False,
                        ) as c:
                            resp = c.get(url)
                            resp.raise_for_status()
                            path.write_bytes(resp.content)
                            downloaded = True
                            break
                    except Exception as e:
                        logger.warning(
                            "Download attempt %d failed: %s",
                            attempt + 1, e,
                        )
                        import time as _time
                        _time.sleep(2 ** attempt)
                if not downloaded:
                    return False

        # Load ONNX session
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as e:
            logger.warning("ONNX session init failed: %s", e)
            return False

        # Load tokenizer
        try:
            from tokenizers import Tokenizer
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
            self._tokenizer.enable_truncation(max_length=256)
            self._tokenizer.enable_padding(length=256)
        except Exception as e:
            logger.warning("Tokenizer init failed: %s", e)
            return False

        self._ready = True
        logger.info("ONNX MiniLM embedder ready (384-dim)")
        return True

    def embed(self, text: str) -> list[float]:
        import numpy as np

        if not self._ensure_model():
            raise RuntimeError("ONNX model not available")

        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        # Mean pooling over token embeddings
        token_embeddings = outputs[0]  # (1, seq_len, 384)
        mask = attention_mask[..., np.newaxis].astype(np.float32)
        pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1)

        # L2 normalize
        vec = pooled[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        result: list[float] = vec.tolist()
        return result

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        if not self._ensure_model():
            return [self.embed(t) for t in texts]

        encodings = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array(
            [e.attention_mask for e in encodings], dtype=np.int64
        )
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        token_embeddings = outputs[0]
        mask = attention_mask[..., np.newaxis].astype(np.float32)
        pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1)

        # L2 normalize each
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        pooled = pooled / norms

        result: list[list[float]] = pooled.tolist()
        return result

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import numpy as np
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        dot = np.dot(va, vb)
        norm_a = np.linalg.norm(va) or 1.0
        norm_b = np.linalg.norm(vb) or 1.0
        return float(dot / (norm_a * norm_b))


# ── Ollama Embedder ──────────────────────────────────────────────────


class OllamaEmbedder:
    """Uses local Ollama for embeddings — best quality, free."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "mxbai-embed-large",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def embed(self, text: str) -> list[float]:
        import httpx
        resp = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if embeddings:
            first: list[float] = embeddings[0]
            return first
        fallback: list[float] = data.get("embedding", [])
        return fallback

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (norm_a * norm_b)


# ── TF-IDF Embedder (fallback) ──────────────────────────────────────


def _simple_stem(word: str) -> str:
    """Minimal suffix-stripping stemmer (no dependencies)."""
    if len(word) <= 3:
        return word
    for suffix in (
        "ation", "tion", "sion", "ness", "ment", "ible", "able",
        "ical", "ism", "ist", "ity", "ure", "ous",
        "ing", "ies", "ive", "ful", "ess", "ize",
        "ed", "ly", "er", "al", "es", "s",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


class TFIDFEmbedder:
    """TF-IDF with bigrams — no dependencies, always available.

    Vocabulary capped at 512 to keep vectors small in SQLite.
    """

    MAX_VOCAB = 512

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self._next_idx = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        raw = re.findall(r"[a-z]+", text.lower())
        stemmed = [_simple_stem(w) for w in raw]
        bigrams = [
            f"{stemmed[i]}_{stemmed[i+1]}"
            for i in range(len(stemmed) - 1)
        ]
        return stemmed + bigrams

    def embed(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        for t in tokens:
            if t not in self._vocab and self._next_idx < self.MAX_VOCAB:
                self._vocab[t] = self._next_idx
                self._next_idx += 1
        dim = min(len(self._vocab), self.MAX_VOCAB)
        if dim == 0:
            return [0.0]
        vec = [0.0] * dim
        for t in tokens:
            idx = self._vocab.get(t)
            if idx is not None and idx < dim:
                vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (norm_a * norm_b)


# ── Embedder selection ───────────────────────────────────────────────


def get_embedder() -> ONNXMiniLMEmbedder | OllamaEmbedder | TFIDFEmbedder:
    """Get the best available embedder.

    Priority: ONNX MiniLM > Ollama (local) > TF-IDF fallback.

    Env overrides:
      ``EDUAGENT_EMBEDDER=tfidf`` — force the dependency-free TF-IDF embedder
          (deterministic and fully offline; this is what CI/tests use so the
          suite never reaches out to HuggingFace).
      ``EDUAGENT_OFFLINE=1`` — never attempt the network model download; pick
          the best *local* embedder (Ollama if it's running, else TF-IDF).

    Robustness: if the ONNX model cannot be obtained — not cached *and* the
    download fails (offline, or a flaky network) — fall back to a working
    embedder instead of returning an ONNX embedder that would raise
    ``RuntimeError("ONNX model not available")`` on every ``embed()`` call.
    """
    pref = os.environ.get("EDUAGENT_EMBEDDER", "").strip().lower()
    if pref in {"tfidf", "tf-idf", "simple"}:
        return TFIDFEmbedder()

    offline = os.environ.get("EDUAGENT_OFFLINE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }

    # 1. ONNX MiniLM — best quality, offline once cached, 384-dim
    if not offline:
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
            embedder = ONNXMiniLMEmbedder()
            # Only commit to ONNX if the model is actually ready (already
            # cached, or it downloads cleanly right now). If it can't be
            # obtained, fall through — returning it unready makes every
            # embed() call raise.
            if embedder._ensure_model():
                return embedder
            logger.info(
                "ONNX MiniLM model unavailable (offline or download failed); "
                "falling back to a lighter embedder for now."
            )
        except ImportError:
            pass

    # 2. Ollama (local server with embedding model)
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            embed_models = [m for m in models if "embed" in m.lower()]
            if embed_models:
                logger.debug("Using Ollama embedder: %s", embed_models[0])
                return OllamaEmbedder(model=embed_models[0])
    except Exception as e:  # Ollama absent / bad response → fall through to TF-IDF
        logger.debug("Ollama embedder probe failed (%s); using TF-IDF", e)

    # 3. TF-IDF fallback — no dependencies, always works
    logger.debug(
        "Using TF-IDF embedder. Install onnxruntime + tokenizers "
        "for much better search quality."
    )
    return TFIDFEmbedder()
