"""Consent-gated, metadata-only ingestion orchestration."""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator

from .adapters.base import AdapterHealth, ProviderAdapter
from .application.ingestion import (
    IngestionRepository,
    SessionMetricComputer,
    SourceIdentifierProtector,
)
from .display_labels import (
    PROJECT_DISPLAY_NAME_MAX_LENGTH,
    SESSION_DISPLAY_NAME_MAX_LENGTH,
    minimize_private_display_name,
)
from .domain import (
    PSEUDONYM_PATTERN,
    Provider,
    SafeEvent,
    SafeSession,
    SourceEvent,
    SourceSession,
    SourceSessionSnapshot,
    StrictModel,
)
from .metrics import compute_session_metrics


class IngestionError(RuntimeError):
    """A sanitized ingestion failure that cannot disclose provider data."""


class ConsentRequiredError(IngestionError):
    """Raised before a non-synthetic adapter is allowed to access its source."""


class AdapterUnavailableError(IngestionError):
    """Raised when an adapter cannot safely provide Phase 1 metadata."""


class IngestionReport(StrictModel):
    provider: Provider
    sessions_seen: int = 0
    sessions_selected: int = 0
    sessions_inserted: int = 0
    sessions_updated: int = 0
    events_seen: int = 0
    events_inserted: int = 0
    events_updated: int = 0
    metrics_written: int = 0
    truncated: bool = False


class IngestionSelection(StrictModel):
    """Safe persisted identifiers that bound a provider import."""

    project_ids: frozenset[str] = Field(default_factory=frozenset)
    session_ids: frozenset[str] = Field(default_factory=frozenset)
    max_sessions: int = Field(default=1000, ge=1, le=1000)

    @field_validator("project_ids", "session_ids")
    @classmethod
    def safe_pseudonyms(cls, values: frozenset[str]) -> frozenset[str]:
        if any(PSEUDONYM_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("ingestion selectors must be safe pseudonyms")
        return values

    @property
    def has_selector(self) -> bool:
        return bool(self.project_ids or self.session_ids)


class IngestionService:
    """Move ephemeral identifiers through HMAC before the database boundary."""

    def __init__(
        self,
        database: IngestionRepository,
        pseudonymizer: SourceIdentifierProtector,
        metric_computer: SessionMetricComputer = compute_session_metrics,
    ):
        self._database = database
        self._pseudonymizer = pseudonymizer
        self._metric_computer = metric_computer

    @staticmethod
    def _private_display_name(
        value: SecretStr | None, *, max_length: int
    ) -> str | None:
        if value is None:
            return None
        return minimize_private_display_name(
            value.get_secret_value(), max_length=max_length
        )

    def _safe_session(self, source: SourceSession) -> SafeSession:
        provider_namespace = source.provider.value
        installation_id = self._pseudonymizer.pseudonymize(
            f"{provider_namespace}:installation",
            source.source_installation_id.get_secret_value(),
        )
        project_id = self._pseudonymizer.pseudonymize(
            f"{provider_namespace}:project:{installation_id}",
            source.source_project_id.get_secret_value(),
        )
        session_id = self._pseudonymizer.pseudonymize(
            f"{provider_namespace}:session:{installation_id}",
            source.source_session_id.get_secret_value(),
        )
        return SafeSession(
            provider=source.provider,
            installation_id=installation_id,
            project_id=project_id,
            session_id=session_id,
            provider_version=source.provider_version,
            adapter_version=source.adapter_version,
            source_schema_version=source.source_schema_version,
            started_at=source.started_at,
            ended_at=source.ended_at,
            terminal_state=source.terminal_state,
            events_complete=source.events_complete,
            project_display_name=self._private_display_name(
                source.source_project_display_name,
                max_length=PROJECT_DISPLAY_NAME_MAX_LENGTH,
            ),
            session_display_name=self._private_display_name(
                source.source_session_display_name,
                max_length=SESSION_DISPLAY_NAME_MAX_LENGTH,
            ),
        )

    def _safe_event(
        self,
        source: SourceEvent,
        session: SafeSession,
    ) -> SafeEvent:
        event_id = self._pseudonymizer.pseudonymize(
            f"{session.provider.value}:event:{session.session_id}",
            source.source_event_id.get_secret_value(),
        )
        return SafeEvent(
            session_id=session.session_id,
            event_id=event_id,
            kind=source.kind,
            sequence=source.sequence,
            occurred_at=source.occurred_at,
            time_basis=source.time_basis,
            duration_ms=source.duration_ms,
            success=source.success,
            tool_category=source.tool_category,
            usage=source.usage,
        )

    def ingest(
        self,
        adapter: ProviderAdapter,
        *,
        page_limit: int = 100,
        selection: IngestionSelection | None = None,
    ) -> IngestionReport:
        """Ingest one provider without retaining identifiers or message content.

        The consent check intentionally precedes ``probe`` and every other adapter
        call.  Synthetic fixtures are the only Phase 1 consent-free source.
        """

        if page_limit < 1 or page_limit > 100:
            raise ValueError("page_limit must be between 1 and 100")

        provider = adapter.provider
        required_tier = adapter.required_consent_tier
        requires_explicit_selection = adapter.requires_explicit_selection
        self._database.initialize()
        if provider is not Provider.SYNTHETIC and not self._database.has_active_consent(
            provider, required_tier
        ):
            raise ConsentRequiredError(
                "explicit source consent is required before provider access"
            )

        if requires_explicit_selection and (selection is None or not selection.has_selector):
            raise ConsentRequiredError(
                "operational history access requires an explicit safe selection"
            )
        effective_selection = selection or IngestionSelection()
        run_id: str | None = None
        sessions_seen = 0
        sessions_inserted = 0
        sessions_selected = 0
        truncated = False
        sessions_updated = 0
        events_seen = 0
        events_inserted = 0
        events_updated = 0
        metrics_written = 0
        try:
            probe = adapter.probe()
            if probe.provider is not provider:
                raise AdapterUnavailableError("adapter provider provenance mismatch")
            if probe.health is not AdapterHealth.READY or not probe.supports_metadata:
                raise AdapterUnavailableError("adapter metadata source is unavailable")
            if requires_explicit_selection and not probe.supports_content:
                raise AdapterUnavailableError("adapter content source is unavailable")

            run_id = self._database.begin_ingestion_run(
                provider=provider,
                provider_version=probe.provider_version,
                adapter_version=probe.adapter_version,
                source_schema_version=probe.source_schema_version,
                data_tier=required_tier,
            )

            cursor: str | None = None
            seen_cursors: set[str] = set()
            stop_listing = False
            while True:
                page = adapter.list_sessions(cursor=cursor, limit=page_limit)
                for source_session in page.sessions:
                    sessions_seen += 1
                    if source_session.provider is not provider:
                        raise AdapterUnavailableError(
                            "session provider provenance mismatch"
                        )
                    if (
                        source_session.provider_version != probe.provider_version
                        or source_session.adapter_version != probe.adapter_version
                        or source_session.source_schema_version
                        != probe.source_schema_version
                    ):
                        raise AdapterUnavailableError(
                            "session version provenance mismatch"
                        )

                    indexed_session = self._safe_session(source_session)
                    selected = (
                        not effective_selection.has_selector
                        or indexed_session.project_id
                        in effective_selection.project_ids
                        or indexed_session.session_id
                        in effective_selection.session_ids
                    )
                    if not selected:
                        continue
                    if sessions_selected >= effective_selection.max_sessions:
                        truncated = True
                        stop_listing = True
                        break
                    sessions_selected += 1

                    snapshot = adapter.read_session(source_session)
                    enriched_session = snapshot.session
                    if (
                        enriched_session.provider is not source_session.provider
                        or enriched_session.source_installation_id.get_secret_value()
                        != source_session.source_installation_id.get_secret_value()
                        or enriched_session.source_project_id.get_secret_value()
                        != source_session.source_project_id.get_secret_value()
                        or enriched_session.source_session_id.get_secret_value()
                        != source_session.source_session_id.get_secret_value()
                        or enriched_session.started_at != source_session.started_at
                    ):
                        raise AdapterUnavailableError(
                            "session detail identity mismatch"
                        )
                    if (
                        enriched_session.provider_version != probe.provider_version
                        or enriched_session.adapter_version != probe.adapter_version
                        or enriched_session.source_schema_version
                        != probe.source_schema_version
                    ):
                        raise AdapterUnavailableError(
                            "session detail provenance mismatch"
                        )

                    safe_session = self._safe_session(enriched_session)
                    safe_events = tuple(
                        self._safe_event(source_event, safe_session)
                        for source_event in snapshot.events
                    )
                    events_seen += len(safe_events)
                    persisted = self._database.persist_session(
                        safe_session, safe_events
                    )
                    sessions_inserted += persisted.session_inserted
                    sessions_updated += persisted.session_updated
                    events_inserted += persisted.events_inserted
                    events_updated += persisted.events_updated

                    # Compute from the safe persisted view so repeated or extended
                    # reads cannot make database rows and metrics disagree.
                    stored_session = self._database.get_session(safe_session.session_id)
                    if stored_session is None:
                        raise IngestionError("safe session persistence failed")
                    stored_events = self._database.get_session_events(
                        safe_session.session_id
                    )
                    observations = self._metric_computer(
                        stored_session, stored_events
                    )
                    metrics_written += self._database.replace_session_metrics(
                        safe_session.session_id, observations
                    )

                if stop_listing:
                    break

                next_cursor = page.next_cursor
                if next_cursor is None:
                    break
                if next_cursor in seen_cursors or next_cursor == cursor:
                    raise AdapterUnavailableError("adapter pagination cursor repeated")
                seen_cursors.add(next_cursor)
                cursor = next_cursor

            report = IngestionReport(
                provider=provider,
                sessions_seen=sessions_seen,
                sessions_selected=sessions_selected,
                sessions_inserted=sessions_inserted,
                sessions_updated=sessions_updated,
                events_seen=events_seen,
                events_inserted=events_inserted,
                events_updated=events_updated,
                metrics_written=metrics_written,
                truncated=truncated,
            )
            self._database.finish_ingestion_run(
                run_id,
                status="completed",
                sessions_seen=sessions_seen,
                events_seen=events_seen,
                metrics_written=metrics_written,
            )
            return report
        except (ConsentRequiredError, AdapterUnavailableError, IngestionError):
            if run_id is not None:
                self._finish_failed_run(
                    run_id, sessions_seen, events_seen, metrics_written
                )
            raise
        except Exception:
            if run_id is not None:
                self._finish_failed_run(
                    run_id, sessions_seen, events_seen, metrics_written
                )
            # Provider exceptions may contain paths, identifiers, or content.  Do
            # not chain or copy them into a user-visible error.
            raise IngestionError("provider metadata ingestion failed") from None

        finally:
            try:
                adapter.close()
            except Exception:
                # Cleanup failures can contain subprocess state. Never surface
                # them or replace the already-sanitized ingestion result.
                pass

    def _finish_failed_run(
        self,
        run_id: str,
        sessions_seen: int,
        events_seen: int,
        metrics_written: int,
    ) -> None:
        try:
            self._database.finish_ingestion_run(
                run_id,
                status="failed",
                sessions_seen=sessions_seen,
                events_seen=events_seen,
                metrics_written=metrics_written,
                error_code="ingestion_error",
            )
        except Exception:
            # Preserve the original sanitized failure and never surface database
            # paths or provider exception details from best-effort bookkeeping.
            return
