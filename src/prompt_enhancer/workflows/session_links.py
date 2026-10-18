"""The pre-Bench link workflow scores the same pairs with both model roles."""
from ..core.session_links import pair_scores


class SessionLinksWorkflow:
    workflow_id = "session-links"
    workflow_version = "1.0.0"
    compatible_core = ">=0.2.0,<0.3.0"
    step_implementations = (("embedding", "pair-embedding.v1"), ("rerank", "pair-reranker.v1"),
                            ("validate", "pair-score-validation.v1"))

    def __init__(self, embedding, reranker):
        # A stage owns loading, bounded execution, cleanup and provenance.
        self.embedding, self.reranker = embedding, reranker

    def run(self, query_ids, cases):
        embedding_rows = self.embedding(cases)
        reranker_rows = self.reranker(cases)
        return pair_scores(query_ids, cases, embedding_rows, reranker_rows)
