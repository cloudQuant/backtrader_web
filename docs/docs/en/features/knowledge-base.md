# Knowledge base and AI chat

Knowledge bases turn team research rules, data dictionaries, post-mortems, and strategy notes into retrievable context. They are not a way to hand every document to a model: the system retrieves chunks belonging to the selected knowledge base, then gives relevant context to the model to formulate an answer.

## Workflow

1. Create a knowledge base in **AI → Knowledge Base**.
2. Upload or create documents and verify their ownership.
3. Index or re-index each document until its status is available.
4. Ask a focused question in **AI → Chat**, then inspect citations and diagnostics.

## Retrieval versus generation

| Stage | Responsibility |
| --- | --- |
| Lexical retrieval | Available by default; finds keywords and relevant context from document chunks, titles, and body text |
| Semantic retrieval | Optional; vector dependencies add semantically similar chunks |
| Reranking/generation | An optional model answers from retrieved context; unrelated full documents should not be treated as evidence |
| Citations | Returns document/chunk or fallback information for human traceability |

In other words, a model can interpret and organize retrieved content, while the knowledge-base scope, index state, and retrieval result constrain what can serve as evidence.

## Common diagnostics

| Code | Meaning and action |
| --- | --- |
| `not_indexed` | The document is not indexed; index or rebuild it. |
| `no_context_found` | An index exists but lacks sufficiently relevant context; use more specific terms, add material, or check the selected knowledge base. |
| `ai_not_configured` | No generation model is enabled/configured; retrieval can still help locate material. |
| `ai_provider_failed` | The model provider is unavailable or failed; check provider configuration, network, and observability logs while retaining retrieval diagnostics. |

## Configuration

Generation uses `AI_CHAT_*` variables. Optional semantic retrieval uses `RAG_VECTOR_ENABLED`, `RAG_EMBEDDING_MODEL`, `RAG_VECTOR_COLLECTION`, and related settings, and requires the backend `rag` extra. Disabling semantic retrieval does not disable lexical retrieval or index-status diagnostics.

Remove account details, secrets, customer information, and unauthorized trading instructions before uploading. See [Configuration](../reference/configuration.md).
