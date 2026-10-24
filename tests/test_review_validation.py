"""Synthetic structured-reply diagnostics never retain rejected values or keys."""
import json

import pytest
from pydantic import ValidationError

from prompt_enhancer.core.prompt_review import parse_commentary_reply, validate_commentary_reply
from prompt_enhancer.core.review_validation import ReviewValidationIssue


@pytest.mark.parametrize("reply,reason,field", [
    ('not JSON: EXAMPLE_RAW_RESPONSE_CANARY', 'invalid_json', 'reply'),
    ('{}', 'empty_review', 'reply'),
    (json.dumps({'EXAMPLE_RAW_RESPONSE_CANARY': 'example rejected text'}), 'extra_field', 'reply'),
    (json.dumps({'findings': [{'aspect': 'goal', 'severity': 'high', 'why': 'Example reason.'}]}), 'missing_field', 'findings[0].suggestion'),
    (json.dumps({'reformulated_elements': [{'element': 'ambiguity', 'suggested': 'Example wording.'}]}), 'enum_mismatch', 'reformulated_elements[0].element'),
    (json.dumps({'findings': [{'aspect': 'goal', 'severity': 'EXAMPLE_RAW_RESPONSE_CANARY', 'why': 'Example reason.', 'suggestion': 'Example suggestion.'}]}), 'enum_mismatch', 'findings[0].severity'),
    (json.dumps({'notes': 'x' * 1001}), 'text_bound', 'notes'),
    (json.dumps({'reformulated_prompt': 'x' * 2500}), 'rewrite_too_long', 'reformulated_prompt'),
    (json.dumps({'notes': None}), 'empty_review', 'reply'),
    ('{"notes":"Example one.","notes":"Example two."}', 'invalid_json', 'reply'),
])
def test_safe_issue_preserves_strict_rejection(reply, reason, field):
    parsed, issue = validate_commentary_reply(reply, prompt_chars=10)
    assert parsed is None and parse_commentary_reply(reply, prompt_chars=10) is None
    assert issue.model_dump() == {'reason': reason, 'field': field}
    assert 'EXAMPLE_RAW_RESPONSE_CANARY' not in issue.model_dump_json()


def test_unknown_nested_key_is_replaced_by_its_known_parent():
    reply = json.dumps({'reformulated_elements': [{'element': 'goal', 'suggested': 'Example wording.',
                                                   'EXAMPLE_RAW_RESPONSE_CANARY': 'example rejected value'}]})
    _, issue = validate_commentary_reply(reply, prompt_chars=10)
    assert issue.model_dump() == {'reason': 'extra_field', 'field': 'reformulated_elements[0]'}


def test_valid_commentary_has_no_issue_and_same_compatibility_result():
    text = '{"notes":"The fictional request is complete."}'
    parsed, issue = validate_commentary_reply(text, prompt_chars=10)
    assert issue is None and parsed == parse_commentary_reply(text, prompt_chars=10)


@pytest.mark.parametrize('field', ['EXAMPLE_RAW_RESPONSE_CANARY', 'findings[10000].why', 'findings[0].unknown', 'notes.extra'])
def test_wire_issue_rejects_arbitrary_paths(field):
    with pytest.raises(ValidationError):
        ReviewValidationIssue(reason='enum_mismatch', field=field)
