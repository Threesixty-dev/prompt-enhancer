from __future__ import annotations

import prompt_enhancer.api as api_module
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings


def test_http_composition_reuses_claim_census_context_and_identifiers(monkeypatch, tmp_path) -> None:
    application = bootstrap_local_application(AppSettings(home=tmp_path))
    captured: dict[str, object] = {}
    constructed_repositories: list[object] = []
    model_repository = application.database.model_ensemble_repository

    def capture_model_repository():
        repository = model_repository()
        constructed_repositories.append(repository)
        return repository

    def capture_create_app(**values):
        captured.update(values)
        return object()

    monkeypatch.setattr(api_module, "create_app", capture_create_app)
    monkeypatch.setattr(application.database, "model_ensemble_repository", capture_model_repository)
    assert application.create_http_app() is not None

    census = captured["claim_grounding_census_service"]
    review = captured["claim_grounding_review_service"]
    link_review = captured["claim_grounding_link_review_service"]
    source = link_review._sources
    assert source._censuses is census
    assert source._runs in constructed_repositories, "link source must use the normal model repository factory"
    assert source._contexts is review._source._review_contexts
    assert source._ids is census._ids is link_review._ids
    assert link_review._contexts is source._contexts
