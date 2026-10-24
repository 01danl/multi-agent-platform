# 08 — RAG Pipeline (Knowledge Bases)

Phase 2 acceptance — a user uploads a document, attaches the knowledge base
to an agent, asks a question, and gets an answer grounded in retrieved
content with verifiable source references — is met end-to-end (tested and
browser-verified).

## Pipeline

```text
Upload (multipart)                      single server process
  -> validate (extension/MIME whitelist, size cap)         \
  -> KnowledgeDocument row (status=pending)                  background task
  -> parse (pypdf | utf-8/latin-1 text)                     /
  -> chunk (paragraph-aware sliding window, 1200/180 chars)
  -> embed (provider abstraction)
  -> DocumentChunk rows (embedding JSON)
  -> status=ready (or failed + error)

Retrieval (knowledge_search tool)
  query -> embed_query
        -> cosine over chunks of the agent's attached KBs (owner-scoped)
        -> top-k with [filename#chunk] citations and scores
```

## Components

### Embeddings (`app/knowledge/embeddings.py`)

`EmbeddingProvider` protocol with two implementations:

- **OpenAI** (`text-embedding-3-small`) — active when `OPENAI_API_KEY` is
  set; real semantic retrieval.
- **Local token-hash** — deterministic hashed bag-of-words with stopword
  filtering. Honest label: keyword retrieval wearing an embedding interface.
  Zero-network fallback so tests and keyless demos exercise the identical
  pipeline. (An earlier character-shingle variant scored unrelated texts at
  cos≈0.52 — noise that made "no-source" tests fail; the regression is
  covered by `test_retrieval_returns_sources`.)

The provider is chosen once at startup and injected into the store — swapping
to a different vendor is one adapter, no pipeline changes.

### Ingestion (`app/knowledge/ingestion.py`)

- Formats: PDF (pypdf), TXT, MD; anything else is rejected with 422 before
  storage. Caps: 50 MB parse guard, 20 MB upload limit (settings), 2M chars.
- Chunking: sliding window preferring paragraph/sentence boundaries; overlap
  keeps boundary context; whitespace-only chunks dropped.

### Storage & retrieval (`app/knowledge/service.py`)

`knowledge_bases` / `knowledge_documents` / `document_chunks` tables.
Embeddings live as JSON float arrays in SQLite with cosine similarity
computed in Python — deliberately small-scale (fine to tens of thousands of
chunks); `KnowledgeStore.search` is the seam for the Qdrant adapter later.

Statuses (`pending → processing → ready | failed`) are visible through the
API and polled by the UI, including failure reasons (e.g. corrupt PDFs).

### The tool

`knowledge_search(query)` — registered in the platform tool registry,
enabled per agent like any tool, but **scoped**:

- KBs come from the agent's `knowledge_base_ids` via `ToolContext`;
- every query filters `owner_id` — cross-user isolation is enforced in SQL,
  not by prompt (tested);
- the tool description instructs grounding and forbids fabricated sources;
  output carries `[filename#chunkN] (score)` prefixes the model can cite;
- empty result returns "No relevant passages found" — the honest no-source
  behavior (tested: unrelated query → empty, never invented).

## Failure scenarios

| Failure | Behavior |
|---|---|
| Unsupported type / oversized | 422/413 before any storage |
| Corrupt PDF | document `failed` with error shown in UI |
| Empty document (no text) | `failed` ("no extractable text") |
| Provider outage mid-ingest | document `failed`; retry by re-upload |
| Unknown KB in agent config | ignored (search returns nothing for it) |

## Deliberately not built yet

Re-ranking, HyDE, GraphRAG, DOCX, per-chunk citations in the message body
(parsed from model text), Qdrant/Postgres vector backends, ingestion job
queue (single-process background task only — restart loses only in-flight
`processing` documents, which are marked failed by the same startup sweep
logic if the process died).
