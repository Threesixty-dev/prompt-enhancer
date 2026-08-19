# Local models and agent access

How to use the models installed on the Models page from other tools, and how
to let a coding agent ask the app about your metrics. Everything stays on the
machine: the model runtime listens on loopback only, the app proxies it under
the app token, and the MCP server speaks over stdio.

## Where things live

- App token: `api.token` in the app home (`%LOCALAPPDATA%\PromptEnhancer` on
  Windows). The dashboard uses a browser session instead; other programs send
  the token.
- Model storage root: `PROMPT_ENHANCER_LOCAL_MODELS_DIR`, or the
  `local-models.path` file in the app home, or `<app home>/local-models`.
  Weights land under `weights/<repo>/`, the llama.cpp runtime under
  `runtimes/llama.cpp/llama-server(.exe)`, the registry in `registry.json`.

## Chat with an active model

Any model shown as *running* on the Models page answers on three equivalent
routes (all OpenAI chat format, `stream: true` supported):

```text
POST /v1/local-models/{alias}/chat/completions
POST /v1/local-models/{alias}/v1/chat/completions      # base URL style, per model
POST /v1/local-models/openai/v1/chat/completions       # one base URL, routed by "model"
GET  /v1/local-models/{alias}/v1/models
GET  /v1/local-models/openai/v1/models                  # every running alias
```

Authentication: `X-Prompt-Enhancer-Token: <token>` or
`Authorization: Bearer <token>`. The second form is what OpenAI clients send,
so they work unchanged with:

```text
base_url = http://127.0.0.1:8765/v1/local-models/openai/v1
api_key  = <contents of api.token>
model    = <alias>          # for example orca27b-iq3m
```

curl, streaming, thinking switched off for a quick answer:

```bash
curl -N -H "Authorization: Bearer $(cat "$LOCALAPPDATA/PromptEnhancer/api.token")" \
  -H "Content-Type: application/json" \
  -d '{"model":"orca27b-iq3m","stream":true,"chat_template_kwargs":{"enable_thinking":false},"messages":[{"role":"user","content":"One sentence: what does git rebase do?"}]}' \
  http://127.0.0.1:8765/v1/local-models/openai/v1/chat/completions
```

Python (`openai` package):

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1/local-models/openai/v1", api_key=open(TOKEN_PATH).read().strip())
reply = client.chat.completions.create(
    model="orca27b-iq3m",
    messages=[{"role": "user", "content": "Write a conventional commit message for: fix retry loop"}],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print(reply.choices[0].message.content)
```

Notes:

- Qwen3-family models think before answering unless `enable_thinking` is
  false; the Models page chat box has it off by default and a toggle.
- Streamed replies are relayed as server-sent events unchanged and capped at
  16 MB; a context overflow comes back as the runtime's HTTP 400 JSON.
- The aliases `openai`, `downloads` and `remote-files` are reserved.
- The runtime port itself is never exposed; only the app's loopback API is.

## Let Codex or Claude Code query your metrics (MCP)

```bash
prompt-enhancer mcp-config
```

prints the snippets for Claude Code (`.mcp.json` / `~/.claude.json`, or the
`claude mcp add` one-liner) and Codex (`~/.codex/config.toml`). The server is
started by the agent itself as a stdio child:

```text
python -m prompt_enhancer mcp --acknowledge-context-egress
```

Without the flag (or `PROMPT_ENHANCER_MCP_ACKNOWLEDGE_CONTEXT_EGRESS=1`) it
prints why it refused and exits with status 2: every value a tool returns
enters the connected model's context and may leave the device through that
model's provider. The tools are read-only and bounded ([ADR 0014](adr/0014-read-only-agent-surface.md)):

| Tool | Returns |
|---|---|
| `list_metric_definitions` | metric key, dimension, name, description, unit, source |
| `list_sessions` | up to 50 sessions per page: ids, provider, project and session names you show in the dashboard, timestamps, terminal state |
| `get_session_metrics` | stored metric results for one session (values or states, coverage, confidence) |
| `summarize_period` | last N days (≤ 365): sessions per provider, top projects, sessions with a known value per metric (≤ 300 most recent, `truncated` flagged) |
| `explain_metric` | the definition and how to read known / unknown / not applicable |
| `get_calibration_status` | rating progress and the local judge's agreement per model (labels only) |

No tool returns transcript text, raw events, file paths, tokens, or model
replies, and there is no generic query.
