"""Validate scores against explicit pairs without selecting or dropping pairs."""
import math


def pair_scores(query_ids, cases, embedding_rows, reranker_rows):
    if len(query_ids) != len(cases) or len(embedding_rows) != len(cases) or len(reranker_rows) != len(cases):
        raise ValueError("invalid_model_score_shape")
    scores = []
    for index, case in enumerate(cases):
        if len(embedding_rows[index]) != len(case.candidates) or len(reranker_rows[index]) != len(case.candidates):
            raise ValueError("invalid_model_score_shape")
        for position, candidate in enumerate(case.candidates):
            embedding = float(embedding_rows[index][position])
            reranker = float(reranker_rows[index][position])
            if not math.isfinite(embedding) or not math.isfinite(reranker):
                raise ValueError("non_finite_model_score")
            scores.append({"query_message_id": query_ids[index], "candidate_message_id": candidate.candidate_id,
                "embedding_score": round(embedding, 8), "reranker_score": round(reranker, 8)})
    return scores
