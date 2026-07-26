from __future__ import annotations

import chromadb

from ..models.chunk import CodeSymbol, SymbolType


class ChromaStore:
    def __init__(self, persist_path: str, collection_name="code_symbols"):
        self._client = chromadb.PersistentClient(path=persist_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, symbols: list[CodeSymbol], embeddings: list[list[float]]) -> None:
        if len(symbols) != len(embeddings):
            raise ValueError("symbols and embeddings must have the same length")
        if not symbols:
            return
        self._collection.upsert(
            ids=[s.id for s in symbols],
            documents=[s.content for s in symbols],
            embeddings=embeddings,
            metadatas=[self._to_metadata(s) for s in symbols],
        )

    def delete_by_file(self, file_path: str) -> None:
        self._collection.delete(where={"file_path": file_path})

    def query(self, query_embedding: list[float], top_k=30) -> list[CodeSymbol]:
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )
        ids = result["ids"][0]
        metadatas = result["metadatas"][0]
        documents = result["documents"][0]
        return [
            self._from_row(symbol_id, metadata, document)
            for symbol_id, metadata, document in zip(ids, metadatas, documents)
        ]

    def count(self) -> int:
        return self._collection.count()

    def get_all(self) -> list[CodeSymbol]:
        result = self._collection.get(include=["metadatas", "documents"])
        ids = result["ids"]
        metadatas = result["metadatas"]
        documents = result["documents"]
        return [
            self._from_row(symbol_id, metadata, document)
            for symbol_id, metadata, document in zip(ids, metadatas, documents)
        ]

    def _to_metadata(self, symbol: CodeSymbol) -> dict:
        return {
            "file_path": symbol.file_path,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "language": symbol.language,
            "name": symbol.name if symbol.name is not None else "",
            "type": symbol.type.value,
            "parent_id": symbol.parent_id if symbol.parent_id is not None else "",
            "fqn": symbol.fqn if symbol.fqn is not None else "",
        }

    def _from_row(self, symbol_id: str, metadata: dict, document: str) -> CodeSymbol:
        return CodeSymbol(
            id=symbol_id,
            parent_id=metadata["parent_id"] or None,
            name=metadata["name"] or None,
            type=SymbolType(metadata["type"]),
            fqn=metadata["fqn"] or None,
            file_path=metadata["file_path"],
            start_line=metadata["start_line"],
            end_line=metadata["end_line"],
            content=document,
            language=metadata["language"],
        )
