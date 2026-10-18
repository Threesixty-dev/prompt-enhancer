"""Reproducibly export the independent core protocol, never application state."""
from pathlib import Path
import json

from prompt_enhancer.enhancement.contracts import Capabilities, ExecuteRequest, ExecutionResult, GenerationContext, Progress, Readiness
from prompt_enhancer.workflows.catalog import catalog

ROOT = Path(__file__).resolve().parents[1] / "contracts" / "enhancement"


def main():
    (ROOT / "workflows.json").write_text(json.dumps(catalog(), indent=2) + "\n")
    for model, name in [(ExecuteRequest, "execute-request"), (ExecutionResult, "execution-result"),
                        (Progress, "progress"), (Readiness, "readiness"), (Capabilities, "capabilities"),
                        (GenerationContext, "generation-context")]:
        (ROOT / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")


if __name__ == "__main__":
    main()
