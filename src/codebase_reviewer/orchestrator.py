from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .context.builder import ContextBuilder
from .indexer.classifier import FileClassifier
from .indexer.embedder import Embedder
from .indexer.graph_builder import GraphBuilder
from .indexer.indexer import Indexer, IndexStats
from .indexer.parser import CodeParser
from .indexer.size_normalizer import SizeNormalizer
from .indexer.walker import Walker
from .llm.client import LLMClient
from .models.chunk import CodeSymbol
from .models.review import ReviewResult
from .retriever.graph_retriever import GraphRetriever
from .retriever.keyword_search import KeywordSearch
from .retriever.ranker import Ranker
from .retriever.retriever import Retriever
from .retriever.semantic_search import SemanticSearch
from .storage.chroma_store import ChromaStore
from .storage.graph_store import GraphStore
from .storage.meta_store import MetaStore


class Orchestrator:
    def __init__(self, repo_path: Path, storage_dir: Path,
                 embedder=None, llm_client=None, top_k=20):
        self.repo_path = Path(repo_path)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.top_k = top_k

        self.classifier = FileClassifier()
        self.parser = CodeParser()
        self.walker = Walker()
        self.size_normalizer = SizeNormalizer(self.parser)
        self.graph_builder = GraphBuilder(self.parser)
        self.embedder = embedder or Embedder()
        self.chroma_store = ChromaStore(persist_path=str(self.storage_dir / "chroma"))
        self.graph_store = GraphStore(str(self.storage_dir / "graph.db"))
        self.meta_store = MetaStore(str(self.storage_dir / "meta.db"))
        self.indexer = Indexer(
            self.classifier, self.parser, self.walker, self.size_normalizer,
            self.graph_builder, self.embedder, self.chroma_store,
            self.graph_store, self.meta_store,
        )
        self.llm = llm_client or LLMClient()
        self.context_builder = ContextBuilder()

    def ensure_indexed(self, force: bool = False) -> IndexStats:
        return self.indexer.index(self.repo_path, force=force)

    def _load_corpus(self) -> list[CodeSymbol]:
        return self.chroma_store.get_all()

    def _build_resolver(self, corpus: list[CodeSymbol]) -> Callable[[str], Optional[CodeSymbol]]:
        by_fqn = {s.fqn: s for s in corpus if s.fqn is not None}
        return lambda fqn: by_fqn.get(fqn)

    def _build_retriever(self, resolver):
        return Retriever(
            SemanticSearch(self.embedder, self.chroma_store),
            KeywordSearch(),
            Ranker(),
            GraphRetriever(self.graph_store, resolver),
        )

    def review(self, query: str, force_index: bool = False) -> ReviewResult:
        self.ensure_indexed(force=force_index)
        corpus = self._load_corpus()
        resolver = self._build_resolver(corpus)
        retriever = self._build_retriever(resolver)
        symbols = retriever.retrieve(query, corpus, top_k=self.top_k)
        context = self.context_builder.build(symbols, query)
        return self.llm.review(context, query)

    def review_stream(self, query: str, force_index: bool = False):
        self.ensure_indexed(force=force_index)
        corpus = self._load_corpus()
        resolver = self._build_resolver(corpus)
        retriever = self._build_retriever(resolver)
        symbols = retriever.retrieve(query, corpus, top_k=self.top_k)
        context = self.context_builder.build(symbols, query)
        yield from self.llm.review_stream(context, query)
