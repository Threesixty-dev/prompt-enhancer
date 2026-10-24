"""Exact input admission with a fictional tokenizer; no model or remote requests."""
from dataclasses import replace
import hashlib
import io
import json
from types import SimpleNamespace
import urllib.request

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers, processors

from prompt_enhancer.enhancement import gateway_nli, nli_tokenizer
from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.infrastructure import litellm
from prompt_enhancer.infrastructure.text_models.manifests import (
    MDEBERTA_XNLI, TEXT_MODEL_MANIFESTS, TextModelTask,
)
from test_gateway_multimodel import payload


@pytest.fixture
def reviewed_tokenizer(tmp_path, monkeypatch):
    model = replace(MDEBERTA_XNLI, key="example_nli", repository_id="example/fictional-nli",
        tokenizer_repository_id="example/fictional-nli", revision="a" * 40,
        tokenizer_revision="a" * 40, weight_sha256="b" * 64, max_sequence_length=8)
    tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2,
        "example": 3, "hypothesis": 4}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    tokenizer.enable_truncation(max_length=8)
    tokenizer.enable_padding(length=32)
    data = tokenizer.to_str().encode()
    monkeypatch.setattr(nli_tokenizer, "ARTIFACTS",
        {model.key: (model.revision, hashlib.sha256(data).hexdigest())})
    monkeypatch.setattr(nli_tokenizer, "ASSET_DIRECTORY", tmp_path)
    manifests = {**TEXT_MODEL_MANIFESTS, model.key: model}
    monkeypatch.setattr(nli_tokenizer, "TEXT_MODEL_MANIFESTS", manifests)
    monkeypatch.setattr(gateway_nli, "TEXT_MODEL_MANIFESTS", manifests)
    path = tmp_path / (model.key + ".json")
    path.write_bytes(data)
    return SimpleNamespace(model=model, data=data, path=path)


@pytest.mark.parametrize("premise,hypothesis,too_long", [
    ("example " * 4, "hypothesis", False),  # 4 + 1 + 3 pair special tokens = 8.
    ("example " * 5, "hypothesis", True),
    ("example " * 4, "hypothesis hypothesis", True),
    ("example " * 200, "hypothesis", True),
    ("x" * 7000, "hypothesis", False),  # Characters are not a token estimate.
    ("\u017c\u00f3\u0142w " * 5, "hypothesis", True),
], ids=["exact_limit", "one_over", "hypothesis_over", "truncation_disabled", "long_single_token", "unicode"])
def test_pair_special_tokens_and_hypothesis_count_without_truncation_or_padding(
        reviewed_tokenizer, premise, hypothesis, too_long):
    assert nli_tokenizer.input_too_long(reviewed_tokenizer.model, premise, hypothesis) is too_long


def evaluator_payload(fixture, words):
    value = payload("classifier")
    value["config"].update(manifest_key=fixture.model.key, model_revision=fixture.model.revision,
        tokenizer_revision=fixture.model.tokenizer_revision)
    value["subject"]["text"] = "example " * words
    value["spec"]["target"] = "hypothesis"
    return value


def forbid_gateway(monkeypatch):
    monkeypatch.setattr(litellm, "LiteLLMNli", lambda *args, **kwargs: pytest.fail("no gateway call permitted"))


def test_oversized_input_is_unknown_before_creating_any_gateway_client(reviewed_tokenizer, monkeypatch):
    forbid_gateway(monkeypatch)
    result = gateway_nli.nli_inference(evaluator_payload(reviewed_tokenizer, 5))
    assert result == {"metric": {"key": "nli.label", "state": "unknown", "reason": "input_too_long",
        "value": None, "label": None}}


def test_at_limit_preserves_full_pair_in_request(reviewed_tokenizer, monkeypatch):
    from test_gateway_multimodel import classifier_reply

    sent = []
    def adapter(settings):
        def invoke(model, body):
            sent.append(json.loads(body))
            return 200, json.dumps(classifier_reply()).encode(), "application/json"
        return invoke
    monkeypatch.setattr(litellm, "LiteLLMNli", adapter)
    value = evaluator_payload(reviewed_tokenizer, 4)
    result = gateway_nli.nli_inference(value)
    assert result["metric"]["label"] == "entailment"
    assert sent == [{"premise": value["subject"]["text"], "hypothesis": "hypothesis",
                     "model_revision": reviewed_tokenizer.model.revision}]


def test_malformed_unicode_is_a_definite_input_failure(reviewed_tokenizer, monkeypatch):
    forbid_gateway(monkeypatch)
    with pytest.raises(CoreError, match="nli_tokenization_failed") as caught:
        nli_tokenizer.input_too_long(reviewed_tokenizer.model, "example \ud800", "hypothesis")
    assert caught.value.uncertain is False


def test_remote_failure_remains_uncertain_after_successful_local_admission(reviewed_tokenizer, monkeypatch):
    monkeypatch.setattr(litellm, "LiteLLMNli", lambda settings: lambda *args: (502, b"{}", "application/json"))
    with pytest.raises(CoreError, match="evaluator_failed") as caught:
        gateway_nli.nli_inference(evaluator_payload(reviewed_tokenizer, 4))
    assert caught.value.uncertain is True


@pytest.mark.parametrize("failure", ["missing", "corrupt", "wrong_revision", "invalid_json", "oversized"])
def test_tokenizer_install_failure_is_definite_local_and_never_calls_gateway(reviewed_tokenizer, monkeypatch, failure):
    fixture = reviewed_tokenizer
    if failure == "missing":
        fixture.path.unlink()
    elif failure == "corrupt":
        fixture.path.write_bytes(b"fictional corrupted artifact")
    elif failure == "wrong_revision":
        monkeypatch.setattr(nli_tokenizer, "ARTIFACTS", {fixture.model.key: ("b" * 40, "c" * 64)})
    elif failure == "invalid_json":
        fixture.path.write_bytes(b"{}")
        monkeypatch.setattr(nli_tokenizer, "ARTIFACTS",
            {fixture.model.key: (fixture.model.revision, hashlib.sha256(b"{}").hexdigest())})
    else:
        monkeypatch.setattr(nli_tokenizer, "MAX_ARTIFACT_BYTES", 16)
    forbid_gateway(monkeypatch)
    with pytest.raises(CoreError, match="nli_tokenizer_unavailable") as caught:
        gateway_nli.nli_inference(evaluator_payload(fixture, 4))
    assert caught.value.uncertain is False


def test_tokenizer_link_is_rejected_without_reading_target(reviewed_tokenizer, monkeypatch):
    fixture = reviewed_tokenizer
    target = fixture.path.with_suffix(".other")
    target.write_bytes(fixture.data)
    fixture.path.unlink()
    try:
        fixture.path.symlink_to(target)
    except OSError:
        pytest.skip("platform requires symlink permission")
    forbid_gateway(monkeypatch)
    with pytest.raises(CoreError, match="nli_tokenizer_unavailable"):
        gateway_nli.nli_inference(evaluator_payload(fixture, 4))


@pytest.mark.parametrize("valid", [True, False])
def test_explicit_staging_uses_only_exact_public_pin_and_preserves_verified_install(
        reviewed_tokenizer, monkeypatch, valid):
    fixture = reviewed_tokenizer
    calls = []
    def open_artifact(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(fixture.data if valid else b"fictional wrong artifact")
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: SimpleNamespace(open=open_artifact))
    if valid:
        nli_tokenizer.stage_artifacts()
        nli_tokenizer.verify_artifacts()
    else:
        with pytest.raises(ValueError, match="nli_tokenizer_integrity"):
            nli_tokenizer.stage_artifacts()
    assert calls == [("https://huggingface.co/example/fictional-nli/resolve/" + "a" * 40 + "/tokenizer.json", 30)]
    assert fixture.path.read_bytes() == fixture.data
    assert not list(fixture.path.parent.glob("*.tmp"))


def test_every_supported_scoped_nli_manifest_has_exact_tokenizer_pin():
    expected = {m.key for m in TEXT_MODEL_MANIFESTS.values() if m.task == TextModelTask.SCOPED_NLI}
    assert set(nli_tokenizer.ARTIFACTS) == expected
    for key, (revision, digest) in nli_tokenizer.ARTIFACTS.items():
        assert revision == TEXT_MODEL_MANIFESTS[key].tokenizer_revision
        assert len(digest) == 64
