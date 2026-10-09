# Graph augmented retrieval

The project now expands its BM25 + FAISS hybrid search through the legal
structure already present in `chunks.json`. Each chunk is associated with its
document, article, and clause. After hybrid retrieval finds relevant chunks,
`GraphRetriever` follows the same clause and same article relationships to add
nearby legal evidence before the RAG layer builds its cited context.

This first graph layer is deterministic and built in memory from the current
corpus. It does not require Neo4j, Microsoft GraphRAG, an API key, or a graph
indexing model. It preserves the existing hybrid retriever and citation
metadata. The Colab audio runtime enables it automatically.

## Use it in Python

```python
from landlaw_rag.retrieval import GraphRetriever

graph_retriever = GraphRetriever(hybrid_retriever, chunks)
hits = graph_retriever.search("Căn cứ xác định giá đất", top_k=6)
```

Each result retains the existing fields and adds `graph_score` and
`graph_relations`. Relations currently include `hybrid_match`, `same_clause`,
and `same_article`.

## Current scope

The graph represents legal hierarchy and expands evidence within the same
clause or article. It does not yet infer legal concepts, amendment edges, or
cross-document references from prose. Those require a validated extraction
step and evaluation against the legal QA test set before they should affect
answers.
