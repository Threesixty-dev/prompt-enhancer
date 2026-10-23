"""Consumes B-owned JSON schemas without depending on the application package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import copy
import re

from jsonschema import Draft202012Validator, SchemaError, ValidationError

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
        catalog = directory / "workflows.json"
        self.workflows = json.loads(catalog.read_text()) if catalog.is_file() else []

    def payload(self):
        return {"schemaVersion": "bench-contracts/v1", "protocolVersion": PROTOCOL,
                "schemas": {key: value.schema for key, value in self.validators.items()}, "workflows": self.workflows}

    @classmethod
    def from_payload(cls, payload):
        def local_references(value, root):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"$id", "$dynamicRef"}:
                        return False
                    if key == "$ref":
                        if not isinstance(child, str) or not child.startswith("#/$defs/"):
                            return False
                        target = root
                        for part in child[2:].split("/"):
                            target = target[part.replace("~1", "/").replace("~0", "~")]
                        if not isinstance(target, (dict, bool)):
                            return False
                    if not local_references(child, root):
                        return False
                return True
            return not isinstance(value, list) or all(local_references(child, root) for child in value)
        try:
            if (payload.get("schemaVersion") != "bench-contracts/v1" or payload.get("protocolVersion") != PROTOCOL
                    or set(payload["schemas"]) != {"execute-request", "execution-result", "progress", "readiness"}
                    or not isinstance(payload["workflows"], list) or len(payload["workflows"]) > 128):
                raise ValueError
            instance = cls.__new__(cls)
            instance.directory, instance.validators = None, {}
            for name, schema in payload["schemas"].items():
                if not isinstance(schema, dict) or not local_references(schema, schema):
                    raise ValueError
                Draft202012Validator.check_schema(schema)
                instance.validators[name] = Draft202012Validator(schema)
            instance.workflows = payload["workflows"]
            return instance
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError, SchemaError):
            raise BenchError("remote_contracts_invalid") from None

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
            if isinstance(node.get("additionalProperties"), dict):
                result = {key: self.normalized(node["additionalProperties"], item) for key, item in result.items()}
            for pattern, child in node.get("patternProperties", {}).items():
                for key in result:
                    if re.search(pattern, key):
                        result[key] = self.normalized(child, result[key])
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
            "consumer": unit.get("consumerBinding", settings["consumerBinding"])
                if unit["strategy"].startswith("consumer.") or unit["strategy"] == "prompt.check.v1" else None,
            "evaluation": settings["evaluatorProfile"], "assertions": unit["assertions"],
            "objective": unit["objective"], "steering": unit["steering"],
        }
        if settings.get("schemaVersion") == "bench-experiment/v2":
            request["workflow"] = settings["workflow"]
            request["workflow_steps"] = unit["stepSettings"]
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
        if settings.get("schemaVersion") == "bench-experiment/v2":
            self.validate_workflow(settings, unit)
        explicit(request["parameters"], schema["properties"]["parameters"])
        return request

    def validate_workflow(self, settings, unit):
        reference = settings["workflow"]
        manifest = next((item for item in self.workflows if all(
            item.get(key) == reference.get(key) for key in ("workflow_id", "version", "definition_sha256")
        )), None)
        if manifest is None:
            raise BenchError("workflow_definition_unsupported")
        if re.fullmatch(manifest["core_version_pattern"], settings["enhancerVersion"]) is None:
            raise BenchError("workflow_core_incompatible")
        if unit["strategy"] != manifest["strategy"]:
            raise BenchError("workflow_strategy_fixed")
        if not set(unit["stepSettings"]) <= set(manifest["configurable_steps"]):
            raise BenchError("workflow_step_not_configurable")
        if unit["assertions"] != settings["harnessAssertions"]:
            raise BenchError("harness_evaluation_fixed")
        step = unit["stepSettings"].get(manifest["model_step"], {})
        binding = step.get("binding") or unit.get("consumerBinding")
        if manifest["model_step"] and not manifest["optional_model"] and not binding:
            raise BenchError("workflow_model_binding_required")
        if any(target.get("evaluator_id") != "diagnostics" for target in unit["objective"].get("targets", [])):
            raise BenchError("workflow_diagnostic_target_unsupported")

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
        if request.get("workflow"):
            if (value.get("workflow") != request["workflow"] or value.get("effective_workflow_steps")
                    != self.normalized(properties["workflow_steps"], request["workflow_steps"])):
                raise BenchError("core_workflow_settings_mismatch", 502)
            receipt = value.get("workflow_result")
            if ((value["status"] == "succeeded" and receipt is None)
                    or receipt is not None and (receipt["workflow"] != request["workflow"]
                        or receipt["definition_sha256"] != request["workflow"]["definition_sha256"])):
                raise BenchError("core_workflow_provenance_mismatch", 502)
        if (value["effective_parameters"] != request["parameters"]
                or value["evaluation_profile"] != self.normalized(properties["evaluation"], request["evaluation"])
                or value["effective_objective"] != self.normalized(properties["objective"], request["objective"])
                or value["effective_steering"] != self.normalized(properties["steering"], request["steering"])
                or value["strategy"] != request["strategy"]
                or value["consumer_binding"] != request["consumer"]):
            raise BenchError("core_effective_settings_mismatch", 502)
        return value
