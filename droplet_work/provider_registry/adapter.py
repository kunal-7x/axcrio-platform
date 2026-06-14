"""provider_registry.adapter — the 3-tier transform (W2). "How add-any-API works."

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §7 (the adapter is the critical decision that makes
"no code deploy" real) + §2b (the 3 tiers) + §6 (field-map injection: JSONPath ONLY, depth<=5,
NEVER eval/Jinja) + §13 R4.

ONE pair the registry calls:
    build_request(def_, cred_plaintext, envelope) -> (url, headers, body)
    parse_response(def_, raw)                      -> response_envelope

THE 3 TIERS (§7):
  * Tier 1 `openai_compat` : ZERO code. body = {model, messages:[{role,content}], **params};
    headers from auth_scheme; response read from $.choices[0].message.content. ~90% of market.
  * Tier 2 `named_provider`: dispatch to named_transforms.NAMED[...] — the EXISTING video
    builders (fal/replicate/luma/...) + anthropic/gemini, REUSED not rewritten.
  * Tier 3 `custom_field_map`: apply request/response maps stored as VALIDATED JSONPath in
    JSONB. The map IS the code. A tiny safe JSONPath subset is implemented INLINE here (no
    third-party dep, no eval, no Jinja). depth<=5 enforced at validate-time AND apply-time.

SECURITY (§6 R4): a user-supplied field-map string is UNTRUSTED. `validate_field_map` rejects
anything that isn't our restricted JSONPath grammar (so an `eval`/`__import__`/template string
is refused at write-time). At apply-time we walk the parsed path mechanically — we NEVER exec
a string. The wire body produced for a `custom_field_map` provider never interpolates a user
string into the URL except the single `{key}` auth token (done in build_request, not the map).

NEVER raises on the hot path: build/parse return a best-effort result or a `failed`/empty
envelope; only `validate_field_map` raises (a FieldMapError) and ONLY at write-time.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import named_transforms
from .schema import AuthScheme, ProviderDef, TransformType

# Hard caps (§6): JSONPath depth and total segment budget — bound the validator + walker.
MAX_PATH_DEPTH = 5
MAX_MAP_ENTRIES = 64

# The dataclass default for ProviderDef.auth_value_tmpl. It is bearer-shaped, so it is treated as
# "unset" for every NON-bearer scheme (so an api_key_header value isn't accidentally "Bearer <key>").
_DEFAULT_BEARER_TMPL = "Bearer {key}"


class FieldMapError(ValueError):
    """Raised ONLY by validate_field_map (write-time). Never on the apply hot path."""


# ---------------------------------------------------------------------------
# The response envelope (§7) — every parse_response returns this exact shape.
# ---------------------------------------------------------------------------
def _empty_response_envelope() -> dict:
    return {
        "text": "",
        "image_url": "",
        "video_url": "",
        "embedding": [],
        "external_id": "",
        "status": "submitted",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_micros": 0,
        "latency_ms": 0,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# AUTH header assembly (shared by Tier 1 + Tier 3). The single {key} token is the
# ONLY interpolation; no user string is ever templated into the URL elsewhere.
# ---------------------------------------------------------------------------
def _auth_headers(def_: ProviderDef, key: str) -> Tuple[Dict[str, str], Optional[Tuple[str, str]]]:
    """Return (headers, query_param) for the def's auth scheme. query_param is
    (name, value) when the scheme puts the key in the query string, else None."""
    scheme = def_.auth_scheme
    scheme = scheme.value if isinstance(scheme, AuthScheme) else str(scheme or "bearer").lower()
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if not key:
        return headers, None
    # `auth_value_tmpl` defaults to the bearer-shaped "Bearer {key}" on the dataclass. That default
    # is meaningful ONLY for the bearer scheme; for a non-bearer scheme it must NOT leak (an
    # api_key_header value should be the raw key, not "Bearer <key>"). So: honor a CUSTOM template
    # (one the operator explicitly set, different from the bearer default), else use the
    # scheme-appropriate default. `_DEFAULT_BEARER_TMPL` is the single sentinel for "unset".
    custom_tmpl = def_.auth_value_tmpl if def_.auth_value_tmpl not in (None, "", _DEFAULT_BEARER_TMPL) \
        else None
    if scheme == AuthScheme.BEARER.value:
        tmpl = def_.auth_value_tmpl or _DEFAULT_BEARER_TMPL
        headers[def_.auth_header_name or "Authorization"] = tmpl.replace("{key}", key)
    elif scheme == AuthScheme.API_KEY_HEADER.value:
        tmpl = custom_tmpl or "{key}"
        headers[def_.auth_header_name or "x-api-key"] = tmpl.replace("{key}", key)
    elif scheme == AuthScheme.API_KEY_QUERY.value:
        return headers, (def_.auth_header_name or "api_key", key)
    elif scheme == AuthScheme.BASIC.value:
        import base64
        token = base64.b64encode(key.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    elif scheme == AuthScheme.OAUTH2_CC.value:
        # OAuth2 client-credentials: the resolved access token is passed as `key`.
        headers["Authorization"] = f"Bearer {key}"
    # AuthScheme.NONE -> no header.
    return headers, None


def _append_query(url: str, qp: Optional[Tuple[str, str]]) -> str:
    if not qp:
        return url
    name, value = qp
    sep = "&" if "?" in url else "?"
    from urllib.parse import quote
    return f"{url}{sep}{quote(name)}={quote(value)}"


# ===========================================================================
# build_request — the request side of the 3 tiers.
# ===========================================================================
def build_request(def_: ProviderDef, key: str, envelope: dict) -> Tuple[str, dict, dict]:
    """Build (url, headers, body) for `def_` from the neutral request envelope.

    Dispatches on `def_.transform_type`. Never raises (a misconfigured def yields a
    best-effort/empty request the HTTP layer will simply fail-closed on)."""
    tt = def_.transform_type
    tt = tt.value if isinstance(tt, TransformType) else str(tt or "openai_compat")

    if tt == TransformType.NAMED_PROVIDER.value:
        nt = named_transforms.get_named_transform(def_.named_provider or "")
        if nt is None:
            return "", {}, {}
        try:
            return nt.build(def_, key, envelope)
        except Exception:  # noqa: BLE001 — fail-closed
            return "", {}, {}

    if tt == TransformType.CUSTOM_FIELD_MAP.value:
        return _build_custom(def_, key, envelope)

    # Default / Tier 1: openai_compat.
    return _build_openai_compat(def_, key, envelope)


def _build_openai_compat(def_: ProviderDef, key: str, envelope: dict) -> Tuple[str, dict, dict]:
    base = (def_.base_url or "").rstrip("/")
    url = f"{base}/v1/chat/completions" if base else "/v1/chat/completions"
    headers, qp = _auth_headers(def_, key)
    url = _append_query(url, qp)
    params = dict(envelope.get("params") or {})
    body: dict = {
        "model": def_.model_default or envelope.get("model") or "",
        "messages": [{"role": "user", "content": envelope.get("prompt", "") or ""}],
    }
    if envelope.get("system"):
        body["messages"].insert(0, {"role": "system", "content": envelope["system"]})
    # passthrough known generation params (don't leak our internal-only keys)
    for k in ("max_tokens", "temperature", "top_p", "stop", "stream", "n", "presence_penalty",
              "frequency_penalty", "response_format"):
        if k in params:
            body[k] = params[k]
    return url, headers, body


def _build_custom(def_: ProviderDef, key: str, envelope: dict) -> Tuple[str, dict, dict]:
    """Tier 3: write envelope fields into the wire body using the request_field_map
    (JSONPath WRITE targets keyed by the SOURCE envelope path). No eval; mechanical walk."""
    base = (def_.base_url or "").rstrip("/")
    url = base or ""
    headers, qp = _auth_headers(def_, key)
    url = _append_query(url, qp)
    body: dict = {}
    fmap = def_.request_field_map or {}
    if isinstance(fmap, dict):
        for source_path, target_path in fmap.items():
            try:
                value = _jsonpath_read(envelope, str(source_path))
                if value is not None:
                    _jsonpath_write(body, str(target_path), value)
            except Exception:  # noqa: BLE001 — a single bad mapping never aborts the build
                continue
    if def_.model_default and "model" not in body:
        body["model"] = def_.model_default
    return url, headers, body


# ===========================================================================
# parse_response — the response side of the 3 tiers.
# ===========================================================================
def parse_response(def_: ProviderDef, raw: Any) -> dict:
    """Parse a raw provider response into the neutral response envelope. Never raises."""
    tt = def_.transform_type
    tt = tt.value if isinstance(tt, TransformType) else str(tt or "openai_compat")

    if tt == TransformType.NAMED_PROVIDER.value:
        nt = named_transforms.get_named_transform(def_.named_provider or "")
        if nt is None:
            out = _empty_response_envelope()
            out["status"] = "failed"
            return out
        try:
            return nt.parse(def_, raw)
        except Exception:  # noqa: BLE001
            out = _empty_response_envelope()
            out["status"] = "failed"
            return out

    if tt == TransformType.CUSTOM_FIELD_MAP.value:
        return _parse_custom(def_, raw)

    return _parse_openai_compat(raw)


def _parse_openai_compat(raw: Any) -> dict:
    out = _empty_response_envelope()
    if isinstance(raw, dict):
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            msg = (choices[0] or {}).get("message") or {}
            if isinstance(msg, dict):
                out["text"] = str(msg.get("content", "") or "")
        usage = raw.get("usage") or {}
        if isinstance(usage, dict):
            out["usage"] = {
                "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "output_tokens": int(usage.get("completion_tokens", 0) or 0),
            }
        out["external_id"] = str(raw.get("id", "") or "")
        out["status"] = "succeeded" if out["text"] else "failed"
        out["raw"] = raw
    else:
        out["status"] = "failed"
    return out


def _parse_custom(def_: ProviderDef, raw: Any) -> dict:
    """Tier 3 response: read raw fields into the envelope via response_field_map
    (envelope target key -> JSONPath READ into the raw response). No eval."""
    out = _empty_response_envelope()
    rmap = def_.response_field_map or {}
    if not isinstance(raw, dict):
        out["status"] = "failed"
        return out
    out["raw"] = raw
    if isinstance(rmap, dict):
        for target_key, source_path in rmap.items():
            try:
                value = _jsonpath_read(raw, str(source_path))
            except Exception:  # noqa: BLE001
                value = None
            if value is not None and target_key in out:
                out[target_key] = value
    # a custom provider that yielded any artifact/text is considered succeeded
    if out.get("text") or out.get("video_url") or out.get("image_url") or out.get("embedding"):
        out["status"] = "succeeded"
    return out


# ===========================================================================
# THE SAFE JSONPath SUBSET (§6 — declarative, no eval, no Jinja, depth-bounded).
# Grammar (deliberately tiny):
#     path     := '$' ( segment )*
#     segment  := '.' KEY  |  '[' INDEX ']'  |  '[' "'" KEY "'" ']'
#     KEY      := [A-Za-z_][A-Za-z0-9_-]*
#     INDEX    := -?[0-9]+
# No filters, no wildcards, no recursion (`..`), no functions, no scripts. This is what
# makes a stored user map SAFE: it can ONLY address a concrete field/index, never execute.
# ===========================================================================
_SEG_RE = re.compile(
    r"""
    \.(?P<dotkey>[A-Za-z_][A-Za-z0-9_-]*)      # .key
    | \[(?P<index>-?\d+)\]                      # [0] / [-1]
    | \[(?P<quote>['"])(?P<qkey>[^'"\]]+)(?P=quote)\]   # ['key'] / ["key"]
    """,
    re.VERBOSE,
)


def parse_jsonpath(path: str) -> List[Any]:
    """Parse our restricted JSONPath into a list of segments (str keys / int indices).

    Raises FieldMapError on anything outside the grammar (this is what refuses eval/Jinja/
    wildcard/recursive strings at WRITE time). Enforces MAX_PATH_DEPTH.
    """
    if not isinstance(path, str):
        raise FieldMapError(f"path must be a string, got {type(path).__name__}")
    s = path.strip()
    if not s.startswith("$"):
        raise FieldMapError(f"path must start with '$': {path!r}")
    rest = s[1:]
    segments: List[Any] = []
    pos = 0
    n = len(rest)
    while pos < n:
        m = _SEG_RE.match(rest, pos)
        if not m or m.start() != pos:
            raise FieldMapError(f"illegal JSONPath segment at offset {pos} in {path!r}")
        if m.group("dotkey") is not None:
            segments.append(m.group("dotkey"))
        elif m.group("index") is not None:
            segments.append(int(m.group("index")))
        elif m.group("qkey") is not None:
            segments.append(m.group("qkey"))
        pos = m.end()
        if len(segments) > MAX_PATH_DEPTH:
            raise FieldMapError(f"JSONPath exceeds max depth {MAX_PATH_DEPTH}: {path!r}")
    return segments


def validate_field_map(field_map: Any) -> bool:
    """Write-time validation of a request/response field map. Returns True if every entry
    is a legal restricted-JSONPath pair; RAISES FieldMapError otherwise (refusing eval/
    template/wildcard/oversized maps). This is the ONLY function that raises."""
    if field_map is None:
        return True
    if not isinstance(field_map, dict):
        raise FieldMapError("field_map must be an object/dict")
    if len(field_map) > MAX_MAP_ENTRIES:
        raise FieldMapError(f"field_map exceeds {MAX_MAP_ENTRIES} entries")
    for k, v in field_map.items():
        # both sides of the map are JSONPaths in our grammar (source path + target path).
        parse_jsonpath(str(k))
        parse_jsonpath(str(v))
    return True


def _jsonpath_read(obj: Any, path: str) -> Any:
    """Mechanically walk a restricted JSONPath over a dict/list. Returns None if any segment
    is missing/out-of-range. NEVER executes the string (it's parsed to segments first)."""
    segments = parse_jsonpath(path)
    cur = obj
    for seg in segments:
        if isinstance(seg, int):
            if isinstance(cur, list) and -len(cur) <= seg < len(cur):
                cur = cur[seg]
            else:
                return None
        else:
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return None
    return cur


def _jsonpath_write(root: dict, path: str, value: Any) -> None:
    """Mechanically write `value` at a restricted-JSONPath target into `root` (a dict),
    creating intermediate dicts as needed. List-index targets are not created (a leaf
    list-index write into a non-existent list is skipped — we only build object paths)."""
    segments = parse_jsonpath(path)
    if not segments:
        return
    cur: Any = root
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        if isinstance(seg, int):
            # writing into a list index that we didn't create -> skip (safety; build objects)
            return
        if last:
            if isinstance(cur, dict):
                cur[seg] = value
            return
        nxt = cur.get(seg) if isinstance(cur, dict) else None
        if not isinstance(nxt, dict):
            nxt = {}
            if isinstance(cur, dict):
                cur[seg] = nxt
        cur = nxt
