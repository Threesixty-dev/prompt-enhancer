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
        result = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f",
                                 str(ROOT / "deployment/bench/compose.yaml"), "config", "--format", "json"],
                                env=os.environ | selected, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=30)
        if result.returncode:
            raise SystemExit("compose_validation_failed")
        for service in json.loads(result.stdout)["services"].values():
            mounts = service.get("tmpfs", [])
            if len(mounts) != 1 or not mounts[0].startswith("/tmp:rw,") or "nosuid" not in mounts[0]:
                raise SystemExit("compose_tmpfs_options_split_or_missing")
    print("Compose syntax and tmpfs validated for default, model CPU and explicit CUDA synthetic configuration.")


if __name__ == "__main__":
    main()
