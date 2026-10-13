"""Consumer-owned gateway configuration with only fictional values."""
import json
from pathlib import Path
import runpy
import tomllib


def test_consumer_catalog_binds_alias_without_inventing_model_limits(tmp_path):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1]
                               / "deployment/bench/consumer_start.py"))
    module["write_codex_config"](tmp_path, "example-model", "https://gateway.example.invalid/v1")
    config = tomllib.loads((tmp_path / "config.toml").read_text())
    catalog_path = Path(config["model_catalog_json"])
    model = json.loads(catalog_path.read_text())["models"][0]
    assert model["slug"] == config["model"] == "example-model"
    assert model["context_window"] is None and model["max_context_window"] is None
    assert model["default_reasoning_level"] is None and model["supported_reasoning_levels"] == []
    assert model["shell_type"] == "disabled" and model["node_repl_disabled"] is True
    assert model["input_modalities"] == ["text"]
    assert config["sandbox_mode"] == "read-only" and config["web_search"] == "disabled"
    assert config["model_providers"]["bench_gateway"]["env_key"] == "LITELLM_API_KEY"
    assert config["model_providers"]["bench_gateway"]["wire_api"] == "responses"
    assert catalog_path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "config.toml").stat().st_mode & 0o777 == 0o600
