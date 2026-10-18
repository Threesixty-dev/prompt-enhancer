"""Default review policies for workflows sharing the pre-Bench logical sequence."""
from types import MappingProxyType

from ..core.prompt_review import PROMPT_CHECK_PROMPT_VERSION, _SYSTEM_PROMPT


REVIEW_POLICIES = MappingProxyType({
    "prompt-check": (PROMPT_CHECK_PROMPT_VERSION, _SYSTEM_PROMPT),
    "prompt-rewrite": ("workflow-rewrite-review.v1", _SYSTEM_PROMPT + " "
        "Focus this review on rewriting the prompt for clarity and testability. "
        "Use the inferred context and deterministic findings to explain needed changes. "
        "Include a reformulated prompt when useful; otherwise return findings or notes without a rewrite."),
    "prompt-clarify": ("workflow-clarify-review.v1", _SYSTEM_PROMPT + " "
        "Focus this review on missing or ambiguous details, including dependencies on earlier context. "
        "Suggest concrete clarification questions or placeholders for missing information. "
        "Include a reformulated prompt when useful; otherwise return findings or notes without a rewrite."),
})
