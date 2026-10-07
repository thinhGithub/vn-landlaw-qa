"""M9 orchestration using unchanged M5-M8 public functions."""
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

from landlaw_rag.generation import (
    INSUFFICIENT_EVIDENCE_MESSAGE, CitationValidationError, build_context,
    build_messages, cite_tagged_answer, expand_article_context, filter_results_by_version,
)
from landlaw_rag.comparison import (
    MISSING_COUNTERPART_MESSAGE, build_comparison_messages,
    build_validation_retry_messages, canonicalize_comparison_structure,
    detect_legal_intent, offset_source_labels, retrieve_comparison_evidence,
    validate_comparison_mapping, validate_comparison_structure,
)


class RAGAdapter:
    def __init__(self, retriever, chunks, tokenizer, generate, context_tokens=2600,
                 top_k=6, top_k_per_side=4, validation_retries=2,
                 strict_citations=True):
        self.retriever, self.chunks, self.tokenizer = retriever, chunks, tokenizer
        self.generate = generate
        self.context_tokens = context_tokens
        self.top_k, self.top_k_per_side = top_k, top_k_per_side
        self.validation_retries = validation_retries
        self.strict_citations = strict_citations

    def _context(self, results):
        expanded = expand_article_context(results, self.chunks, self.context_tokens, self.tokenizer)
        return build_context(expanded, self.tokenizer, max_context_tokens=self.context_tokens)

    def __call__(self, query):
        start = perf_counter()
        mode = detect_legal_intent(query)
        if mode == "comparison":
            separated = retrieve_comparison_evidence(self.retriever, query, top_k_per_side=self.top_k_per_side)
            legacy_context, legacy = self._context(list(separated.legacy))
            current_context, current = self._context(list(separated.current))
            context = offset_source_labels(current_context, len(legacy))
            sources = legacy + current
            missing = not legacy or not current
        else:
            hits = self.retriever.search(query, top_k=self.top_k)
            context, sources = self._context(filter_results_by_version(hits, query))
            missing = not sources
        retrieval_seconds = perf_counter() - start
        generation_seconds = citation_seconds = 0.0
        citations, mappings = [], []
        if missing:
            answer = MISSING_COUNTERPART_MESSAGE if mode == "comparison" else INSUFFICIENT_EVIDENCE_MESSAGE
        elif mode == "qa":
            tick = perf_counter()
            raw = self.generate(build_messages(query, context))
            generation_seconds += perf_counter() - tick
            if raw.strip() == INSUFFICIENT_EVIDENCE_MESSAGE:
                answer = INSUFFICIENT_EVIDENCE_MESSAGE
            else:
                tick = perf_counter()
                cited = cite_tagged_answer(raw, sources, strict=self.strict_citations)
                citation_seconds += perf_counter() - tick
                answer = cited.text
                citations = [asdict(c) for c in cited.citations]
                mappings = [asdict(m) for m in cited.claim_mappings]
        else:
            parts = []
            for sections in ((1, 2), (3, 4)):
                base = build_comparison_messages(query, legacy_context, context, sections=sections)
                messages = base
                for attempt in range(self.validation_retries + 1):
                    tick = perf_counter()
                    raw = canonicalize_comparison_structure(self.generate(messages))
                    generation_seconds += perf_counter() - tick
                    tick = perf_counter()
                    try:
                        headings = ("1. Quy định năm 2013:", "2. Quy định hiện hành:") if sections == (1, 2) else ("3. Điểm giống:", "4. Điểm khác/thay đổi:")
                        lines = [line.strip() for line in raw.splitlines() if line.strip()]
                        if len(lines) != 2 or any(not line.startswith(h) for line, h in zip(lines, headings)):
                            raise CitationValidationError("Output comparison sai cấu trúc.")
                        partial = cite_tagged_answer(raw, sources)
                        validate_comparison_mapping(partial.claim_mappings, legacy, current)
                    except CitationValidationError:
                        if attempt == self.validation_retries:
                            raise
                        messages = build_validation_retry_messages(base, raw, sections)
                    else:
                        parts.append(raw)
                        break
                    finally:
                        citation_seconds += perf_counter() - tick
            tick = perf_counter()
            raw = "\n".join(parts)
            validate_comparison_structure(raw)
            cited = cite_tagged_answer(raw, sources)
            validate_comparison_mapping(cited.claim_mappings, legacy, current)
            citation_seconds += perf_counter() - tick
            answer = cited.text
            citations = [asdict(c) for c in cited.citations]
            mappings = [asdict(m) for m in cited.claim_mappings]
        result = dict(query=query, mode=mode, answer=answer, sources=sources,
                      citations=citations, claim_citation_mapping=mappings,
                      retrieval_seconds=retrieval_seconds, generation_seconds=generation_seconds,
                      citation_seconds=citation_seconds, total_seconds=perf_counter() - start)
        if mode == "comparison":
            result.update(legacy_sources=legacy, current_sources=current)
        return result


def load_colab_rag(project_root, model_name="Qwen/Qwen3-4B-Instruct-2507",
                   strict_citations=True):
    """Load saved indexes, CPU embeddings and NF4 Qwen on a CUDA runtime."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from landlaw_rag.retrieval import (
        BM25Index, BM25Retriever, VectorIndex, VectorRetriever, HybridConfig, HybridRetriever,
    )
    if not torch.cuda.is_available():
        raise RuntimeError("Demo RAG cần Colab T4 GPU. Chọn Runtime > Change runtime type.")
    root = Path(project_root)
    chunks_path = root / "data/processed/chunks.json"
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    bm25 = BM25Index.load(root / "indexes/bm25/bm25_index.json.gz")
    vector = VectorIndex.load(root / "indexes/faiss", device="cpu", load_encoder=True, chunks_path=chunks_path)
    retriever = HybridRetriever(BM25Retriever(bm25), VectorRetriever(vector),
                               HybridConfig(bm25_top_n=20, vector_top_n=20, final_top_k=6, rrf_k=60))
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name, device_map="auto", torch_dtype=torch.float16,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16),
    ).eval()
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    @torch.inference_mode()
    def generate(messages):
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt", truncation=False).to(model.device)
        count = inputs["input_ids"].shape[1]
        if count > 7000:
            raise ValueError("Prompt vượt 7000 tokens; giảm context_tokens.")
        output = model.generate(**inputs, max_new_tokens=512, do_sample=False,
                                repetition_penalty=1.05, pad_token_id=tokenizer.eos_token_id)
        return tokenizer.decode(output[0, count:], skip_special_tokens=True).strip()

    return RAGAdapter(
        retriever, chunks, tokenizer, generate,
        strict_citations=strict_citations,
    )
