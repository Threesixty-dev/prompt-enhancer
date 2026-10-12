"""Consumes B-owned JSON schemas without depending on the application package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import copy

from jsonschema import Draft202012Validator, ValidationError

from .errors import BenchError

PROTOCOL = "enhancement.v1"
IDENTITY = ("experiment_id", "revision", "run_id", "correlation_id", "unit_id", "attempt_id")
CORE_TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "uncertain"}


def execution_id(request: dict) -> str:
    payload = {key: request[key] for key in IDENTITY}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


class Contracts:
    def __init__(self, directory: Path):
        self.directory = directory
        self.validators = {}
        for name in ("execute-request", "execution-result", "progress", "readiness"):
            try:
                schema = json.loads((directory / f"{name}.schema.json").read_text())
                Draft202012Validator.check_schema(schema)
            except (OSError, ValueError):
                raise BenchError("shared_contract_unavailable", 503) from None
            self.validators[name] = Draft202012Validator(schema)

    def validate(self, name: str, value: dict):
        try:
            self.validators[name].validate(value)
        except ValidationError:
            raise BenchError("core_contract_violation", 502) from None
        if value.get("protocol_version") != PROTOCOL:
            raise BenchError("core_protocol_mismatch", 502)
        return value

    def normalized(self, node: dict, value):
        schema = self.validators["execute-request"].schema
        if "$ref" in node:
            node = schema["$defs"][node["$ref"].rsplit("/", 1)[-1]]
        if value is None:
            return None
        for union in ("anyOf", "oneOf"):
            if union in node:
                for option in node[union]:
                    if Draft202012Validator({"$defs": schema.get("$defs", {}), **option}).is_valid(value):
                        return self.normalized(option, value)
        if isinstance(value, dict):
            result = copy.deepcopy(value)
            for key, child in node.get("properties", {}).items():
                if key in result:
                    result[key] = self.normalized(child, result[key])
                elif "default" in child:
                    result[key] = copy.deepcopy(child["default"])
            return result
        if isinstance(value, list) and "items" in node:
            return [self.normalized(node["items"], item) for item in value]
        return value

    def request(self, run: dict, attempt: dict) -> dict:
        settings = run["effective"]
        unit = next(u for u in settings["units"] if u["id"] == attempt["unit_id"])
        subject = next(s for s in settings["subjects"] if s["id"] == attempt["subject_id"])
        request = {
            "protocol_version": PROTOCOL, "data_policy": "synthetic_benchmark",
            "experiment_id": run["stable_id"], "revision": run["revision"],
            "run_id": run["id"], "correlation_id": run["correlation_id"],
            "unit_id": unit["id"], "attempt_id": attempt["id"],
            "subject": {"text": subject["text"], "context": subject["context"]},
            "strategy": unit["strategy"], "parameters": unit["parameters"],
            "consumer": unit.get("consumerBinding", settings["consumerBinding"]) if unit["strategy"].startswith("consumer.") else None,
            "evaluation": settings["evaluatorProfile"], "assertions": unit["assertions"],
            "objective": unit["objective"], "steering": unit["steering"],
        }
        schema = self.validators["execute-request"].schema

        def explicit(value, node):
            if "$ref" in node:
                node = schema["$defs"][node["$ref"].rsplit("/", 1)[-1]]
            if node.get("type") == "object":
                for key, child in node.get("properties", {}).items():
                    if key not in value:
                        raise BenchError("effective_parameters_must_be_explicit", 422)
                    explicit(value[key], child)

        self.validate("execute-request", request)
        explicit(request["parameters"], schema["properties"]["parameters"])
        return request

    def correlated(self, name: str, value: dict, request: dict) -> dict:
        self.validate(name, value)
        if (any(value[key] != request[key] for key in IDENTITY)
                or value["execution_id"] != execution_id(request)):
            raise BenchError("core_correlation_mismatch", 502)
        return value

    def result(self, value: dict, request: dict, core_version: str) -> dict:
        self.correlated("execution-result", value, request)
        if value["core_version"] != core_version:
            raise BenchError("core_version_mismatch", 502)
        if value["status"] not in CORE_TERMINAL:
            raise BenchError("core_result_not_terminal", 502)
        original = request["subject"]["text"]
        if value["original"] != {"sha256": hashlib.sha256(original.encode()).hexdigest(), "characters": len(original)}:
            raise BenchError("core_original_provenance_mismatch", 502)
        candidate = value["enhanced_prompt"]
        expected = None if candidate is None else {"sha256": hashlib.sha256(candidate.encode()).hexdigest(), "characters": len(candidate)}
        if value["candidate"] != expected:
            raise BenchError("core_candidate_provenance_mismatch", 502)
        properties = self.validators["execute-request"].schema["properties"]
        if (value["effective_parameters"] != request["parameters"]
                or value["evaluation_profile"] != self.normalized(properties["evaluation"], request["evaluation"])
                or value["effective_objective"] != self.normalized(properties["objective"], request["objective"])
                or value["effective_steering"] != self.normalized(properties["steering"], request["steering"])
                or value["strategy"] != request["strategy"]
                or value["consumer_binding"] != request["consumer"]):
            raise BenchError("core_effective_settings_mismatch", 502)
        return value
