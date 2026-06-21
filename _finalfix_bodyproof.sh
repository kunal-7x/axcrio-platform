#!/bin/bash
cd /opt/famit-agent || exit 9
VENV=/opt/capsy-agent/.venv/bin/python
echo "=== I) PROVE openai client serializes extra_body into request JSON body ==="
$VENV - <<'PYEOF'
import json, traceback
try:
    import httpx, openai
    captured = {}
    def handler(request: httpx.Request) -> httpx.Response:
        try:
            captured["body"] = json.loads(request.content.decode())
        except Exception as e:
            captured["err"] = repr(e)
        # minimal valid chat.completion response so the client returns cleanly
        return httpx.Response(200, json={
            "id":"x","object":"chat.completion","created":0,"model":"m",
            "choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],
            "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}
        })
    transport = httpx.MockTransport(handler)
    client = openai.OpenAI(api_key="dummy", base_url="https://api.groq.com/openai/v1",
                           http_client=httpx.Client(transport=transport))
    client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role":"user","content":"hi"}],
        max_completion_tokens=220,
        extra_body={"frequency_penalty":0.5, "presence_penalty":0.3},
    )
    body = captured.get("body", {})
    print("REQUEST_BODY_KEYS:", sorted(body.keys()))
    fp = body.get("frequency_penalty"); pp = body.get("presence_penalty")
    print("frequency_penalty in body =", fp, "| presence_penalty in body =", pp)
    assert fp == 0.5 and pp == 0.3, "penalties NOT serialized into request body!"
    print("EXTRA_BODY_SERIALIZED_OK")
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
PYEOF
