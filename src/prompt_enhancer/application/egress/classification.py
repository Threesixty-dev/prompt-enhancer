"""Auditable egress classification with no network implementation.

Future paid/download/update classes are declarations only.  This module has no
socket, URL-fetching, telemetry, or transport dependency.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from ...domain import StrictModel


class EgressClass(StrEnum):
    NONE = "none"
    LOOPBACK_OWNED_SERVICE = "loopback_owned_service"
    SIGNED_UPDATE_ADVISORY = "signed_update_advisory"
    APPROVED_MODEL_DOWNLOAD = "approved_model_download"
    APPROVED_PROVIDER_REQUEST = "approved_provider_request"


class FutureEgressState(StrEnum):
    ACTIVE_LOCAL_ONLY = "active_local_only"
    ACTIVE_EXPLICIT_APPROVAL = "active_explicit_approval"
    IMPLEMENTED_UNCOMPOSED = "implemented_uncomposed"
    DECLARED_UNIMPLEMENTED = "declared_unimplemented"


class EgressRegistration(StrictModel):
    module: str = Field(pattern=r"^prompt_enhancer(?:\.[a-zA-Z0-9_]+)+$")
    egress_class: EgressClass
    state: FutureEgressState
    reason_code: str = Field(pattern=r"^[a-z0-9_]{3,64}$")

    @model_validator(mode="after")
    def prevent_inconsistent_claims(self) -> EgressRegistration:
        if (
            self.egress_class in {EgressClass.NONE, EgressClass.LOOPBACK_OWNED_SERVICE}
            and self.state is not FutureEgressState.ACTIVE_LOCAL_ONLY
        ):
            raise ValueError("local registrations require the local-only state")
        if (
            self.egress_class is EgressClass.SIGNED_UPDATE_ADVISORY
            and self.state is not FutureEgressState.DECLARED_UNIMPLEMENTED
        ):
            raise ValueError("signed update transport is unavailable")
        return self


EGRESS_REGISTRY: tuple[EgressRegistration, ...] = (
    EgressRegistration(module="prompt_enhancer.desktop_overlay", egress_class=EgressClass.LOOPBACK_OWNED_SERVICE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="owned_loopback_probe_and_open"),
    EgressRegistration(module="prompt_enhancer.api", egress_class=EgressClass.NONE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="url_parse_only"),
    EgressRegistration(module="prompt_enhancer.interfaces.http.desktop_identity", egress_class=EgressClass.NONE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="origin_parse_only"),
    EgressRegistration(module="prompt_enhancer.infrastructure.providers.codex_app_server.transports.stdio_jsonl", egress_class=EgressClass.NONE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="bounded_child_stdio_only"),
    EgressRegistration(module="prompt_enhancer.infrastructure.text_models.loader", egress_class=EgressClass.APPROVED_MODEL_DOWNLOAD, state=FutureEgressState.ACTIVE_EXPLICIT_APPROVAL, reason_code="reviewed_public_pin_download_opt_in"),
    # Local model runtimes (ADR 0013): the only direct network use is loopback
    # traffic to an owned llama-server child (free-port bind, health, chat
    # proxy). Weights downloads delegate to huggingface_hub and happen only
    # after a size-confirmed approval through the person's own login.
    EgressRegistration(module="prompt_enhancer.application.local_models", egress_class=EgressClass.LOOPBACK_OWNED_SERVICE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="owned_loopback_model_runtime"),
    # Prompt-check hook (ADR 0015): a Claude Code hook process posting the
    # person's prompt to this app's own loopback API and printing the advice.
    EgressRegistration(module="prompt_enhancer.interfaces.hooks.prompt_check_hook", egress_class=EgressClass.LOOPBACK_OWNED_SERVICE, state=FutureEgressState.ACTIVE_LOCAL_ONLY, reason_code="owned_loopback_prompt_check_hook"),
    EgressRegistration(module="prompt_enhancer.infrastructure.estimator_runners.codex", egress_class=EgressClass.APPROVED_PROVIDER_REQUEST, state=FutureEgressState.IMPLEMENTED_UNCOMPOSED, reason_code="bounded_child_cli_runner_uncomposed"),
)

FUTURE_EGRESS_STATES: dict[EgressClass, FutureEgressState] = {
    EgressClass.SIGNED_UPDATE_ADVISORY: FutureEgressState.DECLARED_UNIMPLEMENTED,
    EgressClass.APPROVED_MODEL_DOWNLOAD: FutureEgressState.ACTIVE_EXPLICIT_APPROVAL,
    EgressClass.APPROVED_PROVIDER_REQUEST: FutureEgressState.IMPLEMENTED_UNCOMPOSED,
}


def classify_network_module(module: str) -> EgressRegistration | None:
    return next((entry for entry in EGRESS_REGISTRY if entry.module == module), None)
