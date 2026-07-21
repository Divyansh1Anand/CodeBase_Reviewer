from __future__ import annotations

import httpx


class Embedder:
    def __init__(self, base_url="http://localhost:11434", model="nomic-embed-text",
                 batch_size=32, timeout=60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            try:
                response = self._client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": batch},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Ollama request failed: {exc}") from exc
            embeddings = response.json().get("embeddings")
            if embeddings is None or len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Ollama returned {0 if embeddings is None else len(embeddings)} "
                    f"embeddings for {len(batch)} inputs"
                )
            vectors.extend(embeddings)
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]
