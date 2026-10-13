"""Validate recipes with reserved example settings, never operator secrets."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    settings = json.loads((ROOT / "deployment/bench/settings.example.json").read_text())
    settings.update({key: f"example-{key.lower()}-not-a-secret" for key in
                     ("BENCH_CONSUMER_API_TOKEN", "BENCH_LITELLM_TOKEN")})
    models = json.loads((ROOT / "deployment/bench/settings.models.example.json").read_text())
    for selected in (settings, settings | models, settings | models | {"BENCH_MODEL_DEVICE": "cuda", "BENCH_GPU_DEVICE": "0"}):
        result = subprocess.run(["docker", "compose", "-f", str(ROOT / "deployment/bench/compose.yaml"), "config", "--quiet"],
                                env=os.environ | selected, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            raise SystemExit("compose_validation_failed")
    print("Compose syntax validated for default, model CPU and explicit CUDA synthetic configuration.")


if __name__ == "__main__":
    main()
