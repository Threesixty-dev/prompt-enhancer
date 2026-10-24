"""Bounded diagnostics with no model text, input values or arbitrary field names."""
from typing import Literal

from pydantic import Field

from ..domain import StrictModel


class ReviewValidationIssue(StrictModel):
    reason: Literal["invalid_json", "schema_mismatch", "enum_mismatch", "missing_field",
                    "extra_field", "text_bound", "collection_bound", "empty_review", "rewrite_too_long"]
    field: str = Field(pattern=r"^(reply|notes|reformulated_prompt|findings(?:\[[0-9]{1,4}\](?:\.(?:aspect|severity|why|suggestion))?)?|reformulated_elements(?:\[[0-9]{1,4}\](?:\.(?:element|original|suggested))?)?)$")


def schema_issue(error) -> ReviewValidationIssue:
    item = error.errors(include_url=False, include_context=False, include_input=False)[0]
    location = item["loc"]
    field = "reply"
    if location and location[0] in {"notes", "reformulated_prompt", "findings", "reformulated_elements"}:
        field = location[0]
        children = {"findings": {"aspect", "severity", "why", "suggestion"},
                    "reformulated_elements": {"element", "original", "suggested"}}
        if field in children and len(location) > 1 and type(location[1]) is int and 0 <= location[1] < 10_000:
            field += f"[{location[1]}]"
            if len(location) > 2 and location[2] in children[location[0]]:
                field += "." + location[2]
    reason = {"literal_error": "enum_mismatch", "missing": "missing_field",
              "extra_forbidden": "extra_field", "string_too_long": "text_bound",
              "string_too_short": "text_bound", "too_long": "collection_bound"}.get(item["type"], "schema_mismatch")
    return ReviewValidationIssue(reason=reason, field=field)
