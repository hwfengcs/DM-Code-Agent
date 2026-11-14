# Chat Completions servers: Xinference and Qwen

[简体中文](local-models.md) · [Getting started](getting-started.en.md) · [Extension source](../examples/openai_compatible.py)

This recipe connects DM to an already running OpenAI-compatible **Chat Completions** server.
Model installation and inference remain the server's responsibility. The example is an explicit
provider extension; it does not change the agent loop or the four built-in providers.

**Validation:** the extension is tested with the real OpenAI SDK and an in-memory HTTP transport.
Tests cover the request path, message roles, authentication isolation, retries, and empty
responses. They do not establish a model's ability to solve maintenance tasks.
A live Xinference/Qwen run has not been recorded for this recipe yet.

## 1. Check the model server

Start your model through Xinference's own interface. Use a chat/instruct model that returns
assistant text in `choices[0].message.content`. With Xinference's usual local port, list the
running models at:

```text
http://127.0.0.1:9997/v1/models
```

Use the returned model **ID/UID**, which may differ from its display name. The base URL passed
to DM should end in `/v1`, not `/v1/chat/completions`.

If authentication is enabled, put the server's key in your workspace `.env`:

```dotenv
DM_COMPATIBLE_API_KEY=your-local-server-key
```

Without this variable or an explicit `--api-key`, the extension sends `local-no-key` as an SDK
placeholder for a server without authentication. It never reuses `OPENAI_API_KEY` or
`DEEPSEEK_API_KEY`. It requires an explicit endpoint and does not fall back to a cloud URL.

## 2. Load the extension

Install DM using [the release wheel](getting-started.en.md#install). Save
[`examples/openai_compatible.py`](../examples/openai_compatible.py) locally and inspect it.
If you cloned the repository, that file is already present. Examples are distributed in the
source repository; the v2.1.0 wheel does not contain this new example.

From your target Git checkout, replace the path and `YOUR_MODEL_UID` below:

```bash
dm-agent "Read the README and summarize the test command. Do not modify files." --extension "/absolute/path/to/openai_compatible.py" --provider openai-compatible --base-url http://127.0.0.1:9997/v1 --model "YOUR_MODEL_UID" --max-steps 8 --trace sessions/local-review.jsonl --show-steps
```

On Windows, use an absolute path such as `"C:/projects/DM-Code-Agent/examples/openai_compatible.py"`.
`--extension` executes the file as Python; load only a file you trust. Do not combine this recipe
with `--no-extensions`, which disables the provider. Always pass your model UID explicitly.

The built-in `--provider openai` calls `/responses`. This extension calls `/chat/completions`,
preserves message roles, and uses the existing bounded retry layer. SDK retries are disabled
to prevent retries multiplying across layers.

## 3. Make a small change and inspect it

After the read-only request succeeds, choose a known bug in a disposable Git checkout:

```bash
dm-agent "Add a regression test for the known retry-limit bug, fix the boundary, and run the relevant tests." --extension "/absolute/path/to/openai_compatible.py" --provider openai-compatible --base-url http://127.0.0.1:9997/v1 --model "YOUR_MODEL_UID" --max-steps 12 --trace sessions/local-repair.jsonl --show-steps
dm-agent-trace analyze sessions/local-repair.jsonl
dm-agent-trace export sessions/local-repair.jsonl --output local-repair.html
git diff
```

Replace the sample task with a specific issue that exists in your checkout. Requests consume
local compute or server credits. A step limit bounds agent actions, not token cost or all model
requests. Inspect the changes and run the relevant tests independently. Export starts with a
structural summary; add `--include-content` only to review and share redacted excerpts.

DM expects its JSON action protocol in ordinary assistant text. It does not use the server's
native function-calling protocol. An API-compatible endpoint does not guarantee that a chosen
model follows this protocol reliably.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Connection refused | The model server is running and the port is correct |
| 404 on `/v1/v1/chat/completions` | Use this SDK extension and a base URL with exactly one `/v1` |
| 404 on `/responses` | Select `--provider openai-compatible` and load the extension |
| Model not found | Copy the exact ID from the server's `/v1/models` response |
| 401 / 403 | Supply `DM_COMPATIBLE_API_KEY`; authentication errors are not retried |
| Empty assistant content | Use a model returning final text; `reasoning_content` alone is rejected |
| JSON parse failures | Check instruction-following ability and context settings; start with a small task |

Validate the adapter without any running server:

```bash
uv run --frozen python -m pytest tests/test_openai_compatible_example.py
```

For a useful bug report, include the DM commit/version, server version, model UID, endpoint path
(without credentials), and error. Do not paste keys or unreviewed session contents.
