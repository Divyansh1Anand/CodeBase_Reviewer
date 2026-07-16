# Codebase Reviewer — Architecture

> **Status:** Building — FileClassifier + Parser + Walker skeleton done & tested; JS/TS catalogs + Walker wiring next
> **Goal:** A tool where the user types a prompt, the system reads the codebase, builds the right context, and passes it to an LLM to review the code according to the prompt.

---

## 1. The Core Problem

A codebase reviewer is an **information retrieval → context construction → LLM reasoning** pipeline.

The hard part is *not* calling the LLM. The hard part is:

> Given a user prompt + a whole codebase, how do we pick the *right* slice of code to feed the LLM so it can review meaningfully — without blowing the context window or missing dependencies?

Everything else is plumbing around this.

---

## 2. How Cursor Does It (The Mental Model We're Applying)

Cursor's "Codebase" feature is a retrieval-augmented generation (RAG) system specialized for code. The pipeline has **5 stages**:

### 2.1 Indexing (once, then incrementally)
- Walk the repo, parse each file into a **tree-sitter AST**.
- Chunk code **along structural boundaries** — a chunk = a function, class, method, top-level block (not fixed character windows).
- Each chunk gets metadata: `{file_path, start_line, end_line, symbol_name, language, symbol_type}`.
- Compute an **embedding** for each chunk.
- Store in a **vector store** (ChromaDB) + a **BM25/keyword index** in parallel.

### 2.2 Code Graph
- While parsing, extract **relationships**: imports, calls, definitions, references.
- Store as a **graph**: nodes = symbols, edges = `imports`, `calls`, `contains`, `references`.
- Answers: "who calls this function?", "what does this file depend on?", "where is this type defined?".

### 2.3 Retrieval (per prompt)
**Hybrid retrieval:**
- **Semantic**: embed the prompt, top-K nearest chunks.
- **Lexical**: BM25 keyword search for exact matches.
- **Fuse** the two ranks (Reciprocal Rank Fusion).
- **Graph expansion**: for each hit, pull in callers/callees/imports.

### 2.4 Context Construction (token budget management)
- Fixed budget (1M tokens for Gemini Flash).
- Rank retrieved chunks by relevance score.
- Pack into budget: most relevant first → dependencies → callers.
- Render each chunk with file path + line numbers so the LLM can cite locations.
- Reserve space for system prompt + user question.

### 2.5 LLM Review
- Send `{system, context, user}`. Stream back the review.

---

## 3. Why "Any Language" Works — Tree-sitter + Pluggable Catalogs

Tree-sitter is a generic incremental parser with a separate grammar per language.

### 3.1 The honest truth about "universal" chunking
There is **no single universal chunker algorithm**. Tree-sitter node-type names differ per language (`import_statement` in JS vs `import_declaration` in Go vs `use_declaration` in Rust). So the accurate architecture is:

> **A generic walker + a per-language catalog of rules.** The walker is generic (~30 lines). The intelligence lives in a catalog of `NodeRule`s per language. Adding a language = writing one catalog module, not touching the walker.

### 3.2 What tree-sitter gives us
- **Symbols**: function names, class names, method names, variable declarations
- **Structure**: nesting, scope boundaries, imports/exports
- **Call sites**: who calls what
- **Dependencies**: imports/requires
- **Exact line ranges** for every symbol

### 3.3 Catalogs are code, not config
Name extraction often needs a small function (tree-sitter exposes children by field name, not clean dotted paths). Catalogs are Python modules exporting rules, some of which carry callables.

---

## 4. Project Decisions (Locked)

| Decision | Choice | Rationale |
|---|---|---|
| **Tech stack** | Python | Best tree-sitter bindings, rich LLM/embedding ecosystem |
| **LLM** | Gemini Flash (1M context) | Huge window lets us send whole modules, simplifies retrieval |
| **Interface** | CLI first → web app later | Clean core; web wraps the same API |
| **LLM path** | Cloud APIs first → local LLMs later | Start fast, add local option later |
| **Vector store** | ChromaDB | Python-native, embedded, easy |
| **Embeddings** | `nomic-embed-text` via Ollama (local) | Free, no API key, runs on the user's machine |
| **Parsing** | Tree-sitter + per-language catalogs | Generic walker + JS/TS catalogs first |
| **Indexing** | Incremental (changed files only) | Track content hashes, re-index only what changed |
| **Review scope** | Based on user's prompt | Retrieval decides which files/folders matter |
| **Containment** | `parent_id` tree (Option B) | Handles symbols AND sub-structural blocks (if/for) uniformly |
| **First languages** | JS, then TS (extends JS) | Hardest catalogs first; stress-tests the architecture |

---

## 5. High-Level Design (HLD)

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│                     CLI (typer/click)                            │
│              $ code-reviewer review ./my-repo "..."              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      ORCHESTRATOR                                │
│         (the brain — coordinates everything)                     │
│                                                                 │
│  1. Check index status (fresh or stale?)                         │
│  2. Trigger indexing if needed                                   │
│  3. Run retrieval pipeline                                       │
│  4. Build context                                                │
│  5. Call LLM + stream response                                  │
└──┬──────────┬──────────────┬──────────────┬─────────────────────┘
   │          │              │              │
   ▼          ▼              ▼              ▼
┌────────┐ ┌────────┐  ┌───────────┐  ┌──────────┐
│INDEXER │ │RETRIEVER│  │CONTEXT    │  │LLM       │
│        │ │        │  │BUILDER    │  │CLIENT    │
│- classify│ │- hybrid│  │           │  │           │
│- parse  │ │  search│  │- rank     │  │- gemini  │
│- chunk  │ │- graph │  │- pack     │  │  flash   │
│- embed  │ │  walk  │  │- budget   │  │- stream  │
│- graph  │ │- rank  │  │           │  │- output  │
│- store  │ │        │  │           │  │           │
└───┬────┘ └───┬────┘  └───────────┘  └──────────┘
    │          │
    ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                              │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ VECTOR STORE │  │ KEYWORD INDEX│  │ CODE GRAPH           │  │
│  │ ChromaDB     │  │ BM25 / FTS5  │  │ symbols + edges      │  │
│  │              │  │              │  │ (imports, calls, refs,│ │
│  │              │  │              │  │  containment)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ META / STATE (SQLite)                                     │  │
│  │ - indexed files, timestamps, content hashes               │  │
│  │ - repo config, index version                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Indexing Pipeline (inside the Indexer)

```
FileClassifier ──► Parser ──► Walker (chunker) ──► SizeNormalizer ──► embed + store
  (extension      (grammar   (catalog-driven)      (split oversized,    + graph
   → language)     per lang)                        merge tiny)
```

### Data Flow — One Review Request

```
User: code-reviewer review ./my-repo "Find security vulnerabilities in auth flow"

  [Orchestrator]
       │
       ├─► Is ./my-repo indexed? ─► run indexing pipeline for new/changed files
       │
       ├─► [Retriever]
       │      ├─ Embed the prompt
       │      ├─ Semantic search ─► top-K from Vector Store
       │      ├─ Keyword search  ─► top-K from Keyword Index
       │      ├─ Fuse + rank (Reciprocal Rank Fusion)
       │      └─ Graph expansion ─► callers/callees/imports
       │
       ├─► [Context Builder]
       │      ├─ Take ranked chunks (with expanded dependencies)
       │      ├─ Dedup using containment (skip child if parent included)
       │      ├─ Pack into 1M token budget
       │      ├─ Format with file paths + line numbers
       │      └─ Reserve room for system + user prompt
       │
       └─► [LLM Client]
              ├─ POST to Gemini Flash API
              ├─ System + Context + User
              └─ Stream response to terminal
```

---

## 6. Low-Level Design (LLD)

### 6.1 Project Structure

```
codebase-reviewer/
├── pyproject.toml
├── .env                               # API keys
├── src/
│   └── codebase_reviewer/
│       ├── __init__.py
│       ├── cli.py                      # CLI entry point (Typer)
│       ├── orchestrator.py             # Main coordinator
│       │
│       ├── indexer/
│       │   ├── __init__.py
│       │   ├── classifier.py          # FileClassifier: extension → language
│       │   ├── parser.py              # Tree-sitter AST parsing
│       │   ├── walker.py              # Generic AST walker (the chunker)
│       │   ├── size_normalizer.py     # Split oversized / merge tiny chunks
│       │   ├── embedder.py            # nomic-embed-text (Ollama) client
│       │   ├── graph_builder.py       # Symbol relationship graph
│       │   └── indexer.py             # Indexing coordinator (incremental)
│       │
│       │   └── catalogs/               # PER-LANGUAGE RULES
│       │       ├── __init__.py         # registry: language → Catalog
│       │       ├── base.py             # Catalog, NodeRule, SymbolType
│       │       ├── javascript.py       # JS rules
│       │       └── typescript.py       # extends javascript + TS-only rules
│       │
│       ├── retriever/
│       │   ├── __init__.py
│       │   ├── semantic_search.py     # ChromaDB vector search
│       │   ├── keyword_search.py      # BM25 keyword search
│       │   ├── ranker.py              # Reciprocal Rank Fusion
│       │   ├── graph_retriever.py     # Graph dependency expansion
│       │   └── retriever.py
│       │
│       ├── context/
│       │   ├── __init__.py
│       │   ├── builder.py            # Token budget manager + containment dedup
│       │   └── formatter.py          # Code → LLM-readable format
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py             # Gemini Flash client
│       │   └── prompts.py            # System/user prompt templates
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── chroma_store.py
│       │   ├── keyword_index.py       # BM25 / SQLite FTS5
│       │   ├── graph_store.py
│       │   └── meta_store.py          # Index state + file hashes
│       │
│       └── models/
│           ├── __init__.py
│           ├── chunk.py               # CodeSymbol (+ SymbolType enum)
│           ├── symbol.py              # GraphEdge
│           └── review.py              # ReviewResult, Finding
│
├── tests/
│   ├── test_classifier.py
│   ├── test_parser.py
│   ├── test_walker.py
│   ├── test_catalogs.py
│   ├── test_size_normalizer.py
│   ├── test_retriever.py
│   ├── test_context_builder.py
│   └── fixtures/                      # Sample code per language
│       └── javascript/
│           ├── functions.js
│           ├── classes.js
│           ├── variable_functions.js
│           └── exports.js
│
└── config/
    └── default.yaml
```

### 6.2 Data Models

#### SymbolType enum (granular categories — no more single "module" dump)

```python
class SymbolType(str, Enum):
    # Structural symbols
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE = "type"

    # Granular module-level categories
    IMPORT = "import"          # import / require
    EXPORT = "export"          # export statements
    REEXPORT = "reexport"      # re-export (export ... from)
    CONSTANT = "constant"      # const bindings (non-function)
    VARIABLE = "variable"      # let / var bindings (non-function)

    # Sub-structural blocks (emitted by SizeNormalizer when splitting oversized chunks)
    IF_BLOCK = "if_block"
    LOOP_BLOCK = "loop_block"
    TRY_BLOCK = "try_block"

    # Anonymous top-level code (side-effects: app.use(...), server.listen(...))
    STATEMENT = "statement"

    # Fallback
    TEXT = "text"              # unknown language → whole file
```

#### CodeSymbol — the single unified model (Option B: parent_id containment)

```python
@dataclass
class CodeSymbol:
    id: str                      # SHA256(file_path + start_line + end_line + type)
    parent_id: str | None        # containment pointer — any node can be a parent
    name: str | None             # "login" for symbols; None for blocks/statements
    type: SymbolType             # one of the enum above
    fqn: str | None              # derived by walking parent_id chain; None for non-symbols
    file_path: str
    start_line: int
    end_line: int
    content: str                 # the actual code text
    language: str
```

**Why `parent_id` (Option B) and not a `scope` string or `scope_path` tuple:**

A bare `scope` string is ambiguous (is `"AuthService.login"` a class or method?), collides across files (two files can both have `class Handler`), and duplicates the FQN. A `scope_path` tuple of names works for symbols but **breaks for sub-structural blocks** — an `if` block has no name, so you'd have to invent synthetic names like `__block_3`, polluting the model with fake entries.

`parent_id` is just a pointer — it makes **no semantic assumptions about what the parent is**. The same field cleanly handles three different shapes:

| Shape | `name` | `fqn` | `parent_id` |
|---|---|---|---|
| Named symbol (class/method/function) | set | set | enclosing symbol's id |
| Anonymous statement (top-level side-effect) | `None` | `None` | `None` or enclosing symbol |
| Sub-structural block (if/for from SizeNormalizer) | `None` | `None` | the oversized function's id |

**How each consumer uses it:**
- **Graph builder**: containment edges `parent --contains--> child`.
- **Context builder (dedup)**: "I have the function AND its child if-block → send the function, skip the child."
- **FQN computation**: walk the `parent_id` chain collecting `name`s → `"AuthService.login"`. Computed once, not stored twice.
- **SizeNormalizer**: creates block children that point at the oversized function's `id`.

**Rule (enforce via test):** the walker must **emit parent before children** — pure traversal order (descend after emitting). This guarantees no dangling `parent_id` refs.

#### GraphEdge

```python
@dataclass
class GraphEdge:
    source: str                  # symbol FQN (or file_path for containment roots)
    target: str                  # symbol FQN
    type: str                    # "calls" | "imports" | "references" | "contains"
    source_file: str
    target_file: str
```

#### Review models

```python
@dataclass
class Finding:
    severity: str                # "critical" | "warning" | "info" | "suggestion"
    file_path: str
    line_range: tuple[int, int]
    description: str
    suggestion: str | None

@dataclass
class ReviewResult:
    summary: str
    findings: list[Finding]
```

### 6.3 Component Interfaces

```python
# indexer/classifier.py
class FileClassifier(Protocol):
    def classify(self, file_path: Path) -> str:
        """Extension (+ project context later) → language tag. Unknown → 'text'."""

# indexer/parser.py
class CodeParser(Protocol):
    def parse(self, source: str, language: str) -> "Tree":
        """Load grammar for language, return tree-sitter Tree."""

# indexer/walker.py  (the chunker)
class Walker(Protocol):
    def chunk(self, tree: "Tree", source: str, file_path: str, language: str) -> list[CodeSymbol]:
        """Look up catalog for language, walk AST, emit CodeSymbols (parent before children)."""

# indexer/size_normalizer.py
class SizeNormalizer(Protocol):
    def normalize(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """Split oversized symbols on sub-structural blocks; merge tiny adjacent ones."""

# indexer/embedder.py
class Embedder(Protocol):
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...

# indexer/graph_builder.py
class GraphBuilder(Protocol):
    def build(self, symbols: list[CodeSymbol]) -> list[GraphEdge]: ...
    def get_neighbors(self, symbol_fqn: str) -> list[CodeSymbol]: ...

# retriever/...
class SemanticSearch(Protocol):
    def search(self, query_embedding: list[float], top_k: int) -> list[CodeSymbol]: ...

class KeywordSearch(Protocol):
    def search(self, query: str, top_k: int) -> list[CodeSymbol]: ...

class Ranker(Protocol):
    def fuse_and_rank(self, semantic_results: list, keyword_results: list) -> list[CodeSymbol]: ...

# context/builder.py
class ContextBuilder(Protocol):
    def build(self, symbols: list[CodeSymbol], budget_tokens: int) -> str: ...

# llm/client.py
class LLMClient(Protocol):
    def review(self, context: str, user_prompt: str) -> ReviewResult: ...
```

### 6.4 Storage Schemas

**ChromaDB — `code_symbols` collection**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | symbol hash ID |
| `embedding` | float[768] | nomic-embed-text vector |
| `document` | string | raw code content |
| `file_path` | metadata | source file |
| `start_line` | metadata | line start |
| `end_line` | metadata | line end |
| `language` | metadata | programming language |
| `name` | metadata | symbol name (nullable) |
| `type` | metadata | SymbolType |
| `parent_id` | metadata | containment pointer (nullable) |
| `fqn` | metadata | fully qualified name (nullable) |

**SQLite — `meta.db`**

```
TABLE indexed_files
  file_path    TEXT PRIMARY KEY
  content_hash TEXT              -- SHA256 of file content
  indexed_at   TIMESTAMP
  language     TEXT

TABLE index_state
  repo_path    TEXT PRIMARY KEY
  version      TEXT              -- index schema version
  last_indexed TIMESTAMP
```

**SQLite — `graph.db`**

```
TABLE symbols
  fqn          TEXT PRIMARY KEY
  name         TEXT
  type         TEXT
  file_path    TEXT
  start_line   INT
  end_line     INT
  chunk_id     TEXT
  parent_id    TEXT              -- containment

TABLE edges
  source_fqn   TEXT
  target_fqn   TEXT
  edge_type    TEXT              -- calls, imports, references, contains
  source_file  TEXT
  target_file  TEXT
  PRIMARY KEY (source_fqn, target_fqn, edge_type)

CREATE INDEX idx_edges_source ON edges(source_fqn);
CREATE INDEX idx_edges_target ON edges(target_fqn);
```

---

## 7. Key Algorithms

### 7.1 Indexing — pipeline order

```
FileClassifier → Parser → Walker → SizeNormalizer → embed → store (ChromaDB + graph)
```

Language detection is a **separate stage before parsing**, because tree-sitter cannot load a grammar without knowing the language. The walker *receives* the language tag; it does not detect it.

### 7.2 FileClassifier

```python
EXTENSION_MAP = {
    ".js": "javascript",  ".jsx": "javascript",  ".mjs": "javascript",  ".cjs": "javascript",
    ".ts": "typescript",  ".tsx": "tsx",          ".mts": "typescript",  ".cts": "typescript",
    ".py": "python",  ".go": "go",  ".rs": "rust",  ".java": "java",
    # ...
}

def classify(file_path) -> str:
    return EXTENSION_MAP.get(file_path.suffix, "text")   # unknown → text fallback
```

**Note**: `.ts` → `typescript` grammar, `.tsx` → `tsx` grammar (different grammars; JSX/TSX files fail to parse with the plain TS grammar). The catalog registry maps both grammars to the JS-family rule set.

### 7.3 Walker (catalog-driven chunking)

```
function chunk(tree, source, file_path, language):
    catalog = REGISTRY[language]
    root = tree.root_node
    symbols = []
    parent_stack = []   # stack of (id, name) for FQN derivation

    walk(root, parent_id=None):
        # 1. Find a rule in the catalog matching node.type
        rule = catalog.match(node)

        # 2. If rule has a descent condition, check it
        #    e.g. lexical_declaration: only treat as FUNCTION if initializer is a function
        if rule and rule.descend_if and not rule.descend_if(node): rule = None

        # 3. Emit a symbol if matched
        if rule:
            name = rule.name_extractor(node)         # callable, not a string path
            symbol = CodeSymbol(parent_id=current_parent_id, name=name, type=rule.category, ...)
            symbols.append(symbol)
            walk_children(node, parent_id=symbol.id) # descend AFTER emitting parent
        else:
            # debug mode: log unmatched node.type so we discover catalog gaps
            log_unmatched(node.type)
            walk_children(node, parent_id=current_parent_id)

    return symbols
```

**Descent rules handle the JS traps:**
- `const f = () => {}` → `lexical_declaration` rule peeks at declarator initializer; if `arrow_function`/`function_expression` → emit FUNCTION (name = variable name); else fall back to CONSTANT.
- `export const f = () => {}` → `export_statement` unwraps → same logic → emit FUNCTION + record EXPORT relationship.
- `export { x } from "./mod"` → `export_statement` with `from` → REEXPORT.

**The walker is generic; all per-language logic lives in catalogs.**

### 7.4 Catalog structure

```python
@dataclass
class NodeRule:
    match_type: str                       # tree-sitter node type to match
    category: SymbolType                  # what to emit
    descend_if: callable | None           # optional gate (e.g. "initializer is a function")
    name_extractor: callable              # node → symbol name (field-name based)

@dataclass
class Catalog:
    rules: list[NodeRule]
    def match(self, node) -> NodeRule | None: ...

# typescript.py:
ts_catalog = Catalog(rules=js_catalog.rules + [interface_rule, type_alias_rule, enum_rule, ...])
```

**Ordered rules + fallback semantics (critical).** A single `match_type` can have multiple rules. `Catalog.match` evaluates them in order and returns the **first rule whose `descend_if` passes** (rules with no `descend_if` always pass → they act as fallbacks). This is how we handle `lexical_declaration`:

```python
# lexical_declaration rules (in order):
Rule("lexical_declaration", FUNCTION,
     descend_if=lambda n: _rhs_is_function(n),        # arrow/function_expression/generator RHS
     name_extractor=lambda n: _var_name(n)),
Rule("lexical_declaration", CONSTANT,                 # fallback, no gate
     name_extractor=lambda n: _var_name(n)),
```

**Gate evaluation lives in `Catalog.match`, not in the walker.** The walker calls `catalog.match(node)` and trusts the returned rule is already resolved (gate passed, fallback chosen). The walker does NOT re-evaluate `descend_if` itself. This keeps the walker dumb and the catalog the single source of per-language intelligence.

**Name extraction uses tree-sitter field access, never dotted strings.** Extractors call `node.child_by_field_name(...)` / navigate named children directly. For `lexical_declaration` the name is the `variable_declarator`'s `name` field; for `function_declaration`/`class_declaration` it's the node's `name` field.

### 7.5 SizeNormalizer (runs AFTER the walker)

Two jobs:

**Split oversized** (e.g. > 500 lines / ~3k tokens):
```
for symbol in symbols:
    if token_count(symbol.content) > MAX:
        block_nodes = find_sub_structural_blocks(symbol)   # if, for, while, try, switch
        for block_node in block_nodes:
            create CodeSymbol(parent_id=symbol.id, name=None,
                              type=IF_BLOCK/LOOP_BLOCK/..., content=block_text)
```

**Merge tiny** (e.g. adjacent `const X = 5`, `const Y = 10` → one CONSTANT chunk):
```
group adjacent module-level statements/declarations smaller than MIN into one chunk
```

> SizeNormalizer reassigns chunk IDs/line ranges for the splits it creates; the graph's `parent_id` links survive because the parent (oversized function) already has a stable id.

### 7.6 Hybrid Retrieval + Rank Fusion

```
1. embed query → query_vector
2. semantic_results = chromadb.query(query_vector, n_results=30)
3. keyword_results  = bm25.search(query_text, top_k=30)
4. fused = RRF(semantic_results, keyword_results, k=60)
5. top = fused[:20]
6. for each symbol in top:
       neighbors = graph.get_neighbors(symbol.fqn)   → callers, callees, imports
7. expanded = top ∪ neighbor_symbols  (deduplicated)
8. return expanded
```

**Reciprocal Rank Fusion (RRF):**
```
score(symbol) = Σ  1 / (60 + rank_i)
    for each ranking list i where symbol appears
```

### 7.7 Context Packing (1M budget) + containment dedup

```
1. Reserve: 2000 tokens (system prompt) + query tokens
2. budget = 1_000_000 - reserved
3. Dedup: if both a parent and its child (parent_id) are in the set,
          drop the child (its text is contained in the parent)
4. Sort remaining symbols by fused score (descending)
5. context = ""
6. for symbol in sorted_symbols:
       tokens = estimate_tokens(symbol.content)   # chars / 3.5
       if current_tokens + tokens > budget: break
       context += format_symbol(symbol)
       current_tokens += tokens
7. return context
```

### 7.8 Chunk Formatting for LLM

```
// File: src/auth/service.js:45-82
// Symbol: AuthService.login (method)

```javascript
async login(email, password) {
  ...
}
```
```

Gives the LLM clear **location, symbol identity, and code**.

---

## 8. Final Decisions (Locked)

1. **Embedding delivery** — `nomic-embed-text` via **Ollama locally** (free, no API key, runs on the user's machine).
2. **Indexing strategy** — **Incremental**: track file content hashes in `meta.db`, re-parse/re-chunk/re-embed only changed files, update ChromaDB + graph for those files only.

### Incremental Indexing — How It Works

```
On review request:
  1. Walk repo → current_files = {file_path: current_hash}
  2. Compare with stored hashes in indexed_files table:
       - new     : in current_files, not in index         → INDEX
       - changed : current_hash != stored_hash            → RE-INDEX
       - deleted : in index, not in current_files         → REMOVE from ChromaDB + graph
       - same    : current_hash == stored_hash            → SKIP
  3. For changed/deleted files: delete their old chunks from ChromaDB + symbols/edges from graph
  4. For new/changed files: classify → parse → chunk → normalize → embed → upsert
  5. Update indexed_files table with new hashes + timestamps
```

### Ollama Embedding Call

```
POST http://localhost:11434/api/embed
{
  "model": "nomic-embed-text",
  "input": ["<chunk content>"]
}
→ { "embeddings": [[...768 floats...]] }
```

Run once before using: `ollama pull nomic-embed-text`

---

## 9. Dependencies

```
pyproject.toml
├── tree-sitter              # Core parser
├── tree-sitter-language-pack   # grammars (modern, maintained successor)
├── tree-sitter-javascript / tree-sitter-typescript   # per-grammar packages (alt)
├── chromadb                 # Vector store
├── ollama / httpx           # Embeddings via local Ollama
├── google-generativeai      # Gemini Flash
├── typer                    # CLI framework
├── tiktoken                 # Token counting
├── rich                     # Pretty terminal output
├── pydantic                 # Data validation
└── python-dotenv            # .env loading
```

---

## 10. CLI Interface

```bash
# Index a repo (called automatically on first review)
$ code-reviewer index ./my-repo

# Review with a prompt
$ code-reviewer review ./my-repo "Find security vulnerabilities in the auth flow"

# Review specific path
$ code-reviewer review ./my-repo/src/auth "Is error handling consistent?"

# Force re-index
$ code-reviewer index ./my-repo --force

# Check index status
$ code-reviewer status ./my-repo
```

---

## 11. Build Order

> **FileClassifier → Parser → Walker + JS catalog → TS catalog → SizeNormalizer → Embedder + ChromaDB → Graph Builder → Retriever → Context Builder → LLM Client → Orchestrator → CLI**

Each step is independently testable. JS + TS catalogs are written first because they're the hardest (exports, variable functions, JSX); proving the pipeline on them de-risks everything else.

---

## 12. Build Progress (verified state)

| # | Component | Status | Tests |
|---|---|---|---|
| 1 | `FileClassifier` | ✅ DONE | `test_classifier.py` — 3 tests pass (extension map, full paths, case-sensitivity) |
| 2 | `Parser` (tree-sitter) | ✅ DONE | `test_parser.py` — 6 tests pass (clean parse, exact node counts, TS/TSX dispatch, unsupported raises) |
| 3 | `Walker` skeleton | ✅ DONE (traversal only) | traversal verified; emits 0 symbols until catalog is wired |
| 4 | `Walker` catalog wiring | ⬜ NEXT | — |
| 5 | JS catalog | ⬜ NEXT | — |
| 6 | TS catalog (extends JS) | ⬜ pending | — |
| 7 | SizeNormalizer | ⬜ pending | — |
| 8+ | Embedder → store → graph → retriever → context → LLM → orchestrator → CLI | ⬜ pending | — |

### Environment
- Python 3.14.6 (note: `pyproject.toml` declares `>=3.10`; code uses no 3.11+ syntax so the floor holds)
- tree-sitter 0.26.0, tree-sitter-javascript, tree-sitter-typescript installed

### Existing test fixtures (`tests/fixtures/javascript/`) — verified node-type counts

These counts are the **golden-file guards** for the JS catalog. The catalog must emit symbols that match these structures.

| Fixture | Named-node counts (verified) |
|---|---|
| `variable_functions.js` | `arrow_function`=6, `function_expression`=2, `generator_function`=1, `export_statement`=1, `lexical_declaration`=8 |
| `classes.js` | `class_declaration`=3, `method_definition`=7, `field_definition`=1, `export_statement`=2 |
| `nested_methods.js` | `arrow_function`=3, `function_declaration`=2, `class_declaration`=2, `method_definition`=4, `lexical_declaration`=2 |

### What "done" means for the next step (JS catalog + walker wiring)
The walker emits 0 symbols today because `_lookup_catalog` returns `None`. "Done" = walker emits the correct `CodeSymbol` list for each fixture, verified by a new `test_walker.py` that asserts **emitted symbol counts + types + parent_id relationships** (not just AST node counts). Example expectations for `classes.js`: 3 `CLASS` symbols each containing their `METHOD` children linked via `parent_id`.
