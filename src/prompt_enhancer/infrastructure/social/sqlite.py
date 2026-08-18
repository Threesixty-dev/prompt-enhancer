"""Independent SQLite schema boundary for future local social metadata.

This module deliberately does not import the analyzer database, its migrations,
or its identifiers.  It owns ``social.sqlite3`` and a separate
``social_schema_migrations`` ledger.  The schema is a persistence foundation,
not a composed adapter: the current development service remains in memory and
reports durable sync as unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3

from ...config import lexical_absolute_path, path_has_symlink_component


SOCIAL_DATABASE_FILENAME = "social.sqlite3"
SOCIAL_SCHEMA_VERSION = 1

_SOCIAL_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS social_accounts (
    organization_id TEXT NOT NULL CHECK (
        length(organization_id) = 68 AND substr(organization_id, 1, 4) = 'soc_'
        AND substr(organization_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    account_id TEXT NOT NULL CHECK (
        length(account_id) = 68 AND substr(account_id, 1, 4) = 'soc_'
        AND substr(account_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    state TEXT NOT NULL CHECK (state IN ('active', 'suspended', 'deleted')),
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    PRIMARY KEY (organization_id, account_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_devices (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    device_id TEXT NOT NULL CHECK (
        length(device_id) = 68 AND substr(device_id, 1, 4) = 'soc_'
        AND substr(device_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    account_id TEXT NOT NULL CHECK (length(account_id) = 68),
    state TEXT NOT NULL CHECK (state IN ('active', 'revoked')),
    signing_key_version INTEGER NOT NULL CHECK (signing_key_version > 0),
    agreement_key_version INTEGER NOT NULL CHECK (agreement_key_version > 0),
    signing_key_fingerprint TEXT NOT NULL CHECK (length(signing_key_fingerprint) = 64),
    agreement_key_fingerprint TEXT NOT NULL CHECK (length(agreement_key_fingerprint) = 64),
    enrolled_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (organization_id, device_id),
    FOREIGN KEY (organization_id, account_id)
        REFERENCES social_accounts (organization_id, account_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_relationship_metadata (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    relationship_id TEXT NOT NULL CHECK (length(relationship_id) = 68),
    first_account_id TEXT NOT NULL CHECK (length(first_account_id) = 68),
    second_account_id TEXT NOT NULL CHECK (length(second_account_id) = 68),
    relationship_kind TEXT NOT NULL CHECK (
        relationship_kind IN ('friend_request', 'friendship', 'block')
    ),
    lifecycle_state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    changed_at TEXT,
    PRIMARY KEY (organization_id, relationship_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_conversation_metadata (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    conversation_id TEXT NOT NULL CHECK (length(conversation_id) = 68),
    conversation_kind TEXT NOT NULL CHECK (
        conversation_kind IN ('direct', 'private_group')
    ),
    current_key_version INTEGER NOT NULL CHECK (current_key_version > 0),
    invitation_only INTEGER NOT NULL CHECK (invitation_only = 1),
    discoverable INTEGER NOT NULL CHECK (discoverable = 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, conversation_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_message_envelope_metadata (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    envelope_id TEXT NOT NULL CHECK (length(envelope_id) = 68),
    conversation_id TEXT NOT NULL CHECK (length(conversation_id) = 68),
    message_id TEXT NOT NULL CHECK (length(message_id) = 68),
    sender_account_id TEXT NOT NULL CHECK (length(sender_account_id) = 68),
    sender_device_id TEXT NOT NULL CHECK (length(sender_device_id) = 68),
    operation TEXT NOT NULL CHECK (operation IN ('create', 'edit', 'delete')),
    revision INTEGER NOT NULL CHECK (revision > 0),
    key_version INTEGER NOT NULL CHECK (key_version > 0),
    ciphertext_size INTEGER NOT NULL CHECK (ciphertext_size > 0),
    ciphertext_sha256 TEXT NOT NULL CHECK (length(ciphertext_sha256) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, envelope_id),
    FOREIGN KEY (organization_id, conversation_id)
        REFERENCES social_conversation_metadata (organization_id, conversation_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_file_manifest_metadata (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    manifest_id TEXT NOT NULL CHECK (
        length(manifest_id) = 68 AND substr(manifest_id, 1, 4) = 'shr_'
        AND substr(manifest_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    owner_account_id TEXT NOT NULL CHECK (length(owner_account_id) = 68),
    owner_device_id TEXT NOT NULL CHECK (length(owner_device_id) = 68),
    content_kind TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    chunk_size INTEGER NOT NULL CHECK (chunk_size > 0),
    whole_file_sha256 TEXT NOT NULL CHECK (length(whole_file_sha256) = 64),
    merkle_root_sha256 TEXT NOT NULL CHECK (length(merkle_root_sha256) = 64),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (organization_id, manifest_id)
) STRICT;

CREATE TABLE IF NOT EXISTS social_file_grant_metadata (
    organization_id TEXT NOT NULL CHECK (length(organization_id) = 68),
    grant_id TEXT NOT NULL CHECK (
        length(grant_id) = 68 AND substr(grant_id, 1, 4) = 'shr_'
        AND substr(grant_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    manifest_id TEXT NOT NULL CHECK (length(manifest_id) = 68),
    owner_account_id TEXT NOT NULL CHECK (length(owner_account_id) = 68),
    recipient_account_id TEXT NOT NULL CHECK (length(recipient_account_id) = 68),
    state TEXT NOT NULL CHECK (
        state IN ('offered', 'consented', 'declined', 'revoked', 'expired')
    ),
    offered_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    revoked_at TEXT,
    PRIMARY KEY (organization_id, grant_id),
    FOREIGN KEY (organization_id, manifest_id)
        REFERENCES social_file_manifest_metadata (organization_id, manifest_id)
) STRICT;
"""


@dataclass(frozen=True, slots=True)
class SocialSqliteDatabase:
    path: Path

    @classmethod
    def under(cls, app_home: Path) -> SocialSqliteDatabase:
        return cls(path=lexical_absolute_path(app_home) / SOCIAL_DATABASE_FILENAME)

    def _validated_path(self) -> Path:
        candidate = lexical_absolute_path(self.path)
        if candidate.name != SOCIAL_DATABASE_FILENAME:
            raise ValueError("social database must use its dedicated filename")
        if path_has_symlink_component(candidate.parent):
            raise ValueError("social database parent contains a link or reparse point")
        if path_has_symlink_component(candidate):
            raise ValueError("social database is a link or reparse point")
        return candidate

    def initialize(self) -> int:
        path = self._validated_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path_has_symlink_component(path.parent):
            raise ValueError("social database parent changed during initialization")
        if path_has_symlink_component(path):
            raise ValueError("social database path is a link or reparse point")
        connection = sqlite3.connect(path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS social_schema_migrations (
                    version INTEGER PRIMARY KEY CHECK (version > 0),
                    applied_at TEXT NOT NULL
                ) STRICT
                """
            )
            current_row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM social_schema_migrations"
            ).fetchone()
            current = int(current_row[0]) if current_row is not None else 0
            if current > SOCIAL_SCHEMA_VERSION:
                raise RuntimeError("social database schema is newer than this build")
            if current < 1:
                for statement in _SOCIAL_SCHEMA_V1.split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute(
                    "INSERT INTO social_schema_migrations(version, applied_at) VALUES (?, ?)",
                    (1, datetime.now(UTC).replace(microsecond=0).isoformat()),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows ACL enforcement belongs to an installer/platform adapter.
            pass
        if path_has_symlink_component(path):
            raise ValueError("social database changed into a link or reparse point")
        return SOCIAL_SCHEMA_VERSION


__all__ = [
    "SOCIAL_DATABASE_FILENAME",
    "SOCIAL_SCHEMA_VERSION",
    "SocialSqliteDatabase",
]
