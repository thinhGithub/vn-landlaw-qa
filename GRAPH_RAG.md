# Graph-Augmented Retrieval

The existing hybrid retriever can be wrapped by `GraphRetriever`. It builds an
in-memory hierarchy from parsed chunks and expands hybrid seed hits over
bounded, weighted legal relations. The graph stays local and does not require a
graph database or an extraction model.

## Relations and provenance

Supported relations are:

- `same_article` and `same_clause`, derived from parsed metadata.
- `amends_article`, extracted from Law 43/2024 Article 1 amendment clauses and
  resolved to the corresponding article in Law 31/2024.
- `replaces_article`, recognized for explicit replacement phrasing. No such
  article replacement edge was found in the current corpus.
- `references_article`, extracted from explicit Law 254/2025 article
  references, including named Law 45/2013 references where present.

Each legal-reference edge stores its source chunk ID, source file, character
span, and matched text. Retrieved chunks retain their original IDs and metadata.
The graph snapshot can be inspected or saved with `GraphRetriever.save(path)`.

## Bounded expansion

`GraphConfig` controls seed count, maximum hops, maximum added chunks, maximum
neighbors per node, hop decay, allowed relations, and relation weights. The
defaults use one hop and a 24-chunk expansion budget. Hybrid scores seed the
ranking; relation weight and hop decay score graph-added evidence.

`configs/pipeline.yaml` contains the active settings. The Colab audio runtime
loads those settings and still applies the existing version isolation before
building QA or comparison context. Citation validation continues to use the
retrieved chunks as its evidence set.

```python
from landlaw_rag.retrieval import GraphConfig, GraphRetriever

graph = GraphRetriever(hybrid_retriever, chunks, GraphConfig(max_hops=1))
hits = graph.search("Nghị quyết 254 quy định gì về giá đất?", top_k=6)
```

## Evaluation

The paired retrieval set is `data/evaluation/graph_retrieval.jsonl`. Its legal
unit labels are selectors over document, article, clause, and point rather than
generated chunk IDs. Run BM25 + FAISS Hybrid against Hybrid + Graph with:

```powershell
python scripts/evaluate_graph.py --device cpu
```

For Colab retrieval evaluation and optional end-to-end Qwen QA output, use
[`10_graph_rag_colab.ipynb`](10_graph_rag_colab.ipynb).

The report includes Recall@k, Precision@k, MRR@k, and nDCG@k overall and by
relation focus, plus retrieval latency. It can also write a graph snapshot with
`--graph-snapshot`.
Optional human answer and citation review scores can be added using
`data/evaluation/answer_judgments.template.jsonl` and `--judgments`; blanks are
ignored. The judgments should be completed against the actual generated answer
and its cited source mapping. When `cited_chunk_ids` are supplied, the report
also calculates overlap precision/recall against the labeled legal units.
Claim-level citation support and answer correctness still require human review;
retrieval metrics alone do not establish either.

The current labels are a small pilot, not a statistically representative
benchmark. Replacement patterns are implemented but unexercised in this
corpus. Inspect provenance and expand expert-reviewed labels before changing
relation weights for production use.
