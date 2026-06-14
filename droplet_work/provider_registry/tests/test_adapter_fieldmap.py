"""Offline test suite for provider_registry.adapter + named_transforms (W2).

Spec acceptance (PROVIDER-FRAMEWORK-PLAN §10.5 / §14 W2):
  * openai_compat round-trips a mock OAI response;
  * a named_provider (fal) BYTE-MATCHES the existing media_gen/video/providers golden
    (proves REUSE-not-rewrite, zero drift);
  * a custom_field_map applies JSONPath AND REFUSES a non-JSONPath / eval string.

No network I/O. Run standalone: python -m provider_registry.tests.test_adapter_fieldmap
"""
from __future__ import annotations

import sys

from provider_registry import adapter
from provider_registry.adapter import FieldMapError
from provider_registry import named_transforms
from provider_registry.schema import (
    AuthScheme,
    ProviderDef,
    TransformType,
)

# The live golden — the EXISTING video builders we register, imported directly to compare bytes.
from media_gen.video import providers as golden_providers
from media_gen.video.schema import VideoBrief


def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    # ===================== Tier 1: openai_compat =====================
    def t_oai_build():
        d = ProviderDef(slug="ollama", base_url="https://oai.example.com",
                        auth_scheme=AuthScheme.BEARER, model_default="qwen2.5",
                        transform_type=TransformType.OPENAI_COMPAT)
        env = {"capability": "text_gen", "prompt": "hello",
               "params": {"max_tokens": 64, "temperature": 0.5}}
        url, headers, body = adapter.build_request(d, "sk-abc", env)
        assert url == "https://oai.example.com/v1/chat/completions", url
        assert headers["Authorization"] == "Bearer sk-abc", headers
        assert body["model"] == "qwen2.5"
        assert body["messages"] == [{"role": "user", "content": "hello"}], body
        assert body["max_tokens"] == 64 and body["temperature"] == 0.5
    check("oai_compat_build", t_oai_build)

    def t_oai_parse():
        d = ProviderDef(transform_type=TransformType.OPENAI_COMPAT)
        raw = {"id": "cmpl-1", "choices": [{"message": {"content": "world"}}],
               "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
        out = adapter.parse_response(d, raw)
        assert out["text"] == "world", out
        assert out["status"] == "succeeded"
        assert out["usage"] == {"input_tokens": 3, "output_tokens": 1}
        assert out["external_id"] == "cmpl-1"
    check("oai_compat_parse", t_oai_parse)

    def t_oai_api_key_header():
        d = ProviderDef(base_url="https://x.example.com", auth_scheme=AuthScheme.API_KEY_HEADER,
                        auth_header_name="x-api-key", transform_type=TransformType.OPENAI_COMPAT)
        _, headers, _ = adapter.build_request(d, "K123", {"prompt": "p"})
        assert headers["x-api-key"] == "K123", headers
    check("oai_api_key_header", t_oai_api_key_header)

    def t_oai_api_key_query():
        d = ProviderDef(base_url="https://x.example.com", auth_scheme=AuthScheme.API_KEY_QUERY,
                        auth_header_name="key", transform_type=TransformType.OPENAI_COMPAT)
        url, _, _ = adapter.build_request(d, "QK", {"prompt": "p"})
        assert url.endswith("/v1/chat/completions?key=QK"), url
    check("oai_api_key_query", t_oai_api_key_query)

    # ===================== Tier 2: named_provider (fal) BYTE-MATCH golden =====
    def t_named_fal_bytematch():
        nt = named_transforms.get_named_transform("fal")
        assert nt is not None, "fal named transform must be registered (media_gen reused)"
        d = ProviderDef(slug="fal-wan26", named_provider="fal",
                        model_default="fal-ai/wan-2.6/text-to-video",
                        transform_type=TransformType.NAMED_PROVIDER)
        env = {
            "tenant_id": "t1", "prompt": "a red car",
            "params": {"duration_s": 6, "aspect_ratio": "9:16", "resolution": "720p",
                       "webhook_url": "https://cb.example.com/hook"},
        }
        url, headers, body = nt.build(d, "FALKEY", env)
        # The GOLDEN: call the existing builder directly with the equivalent brief.
        brief = VideoBrief.from_any({
            "tenant_id": "t1", "prompt": "a red car", "duration_s": 6,
            "aspect_ratio": "9:16", "resolution": "720p",
        })
        g_url, g_headers, g_body = golden_providers.build_submit(
            "fal", brief, "fal-ai/wan-2.6/text-to-video", "FALKEY",
            "https://cb.example.com/hook")
        assert url == g_url, f"URL drift: {url!r} != golden {g_url!r}"
        assert headers == g_headers, f"HEADERS drift: {headers} != {g_headers}"
        assert body == g_body, f"BODY drift: {body} != {g_body}"
        # explicit: fal uses the Key auth + queue url
        assert url == "https://queue.fal.run/fal-ai/wan-2.6/text-to-video?fal_webhook=https://cb.example.com/hook"
        assert headers["Authorization"] == "Key FALKEY"
    check("named_fal_bytematch_golden", t_named_fal_bytematch)

    def t_named_fal_parse():
        nt = named_transforms.get_named_transform("fal")
        d = ProviderDef(named_provider="fal", transform_type=TransformType.NAMED_PROVIDER)
        raw = {"request_id": "req-9", "status": "COMPLETED",
               "video": {"url": "https://cdn/v.mp4"}}
        out = nt.parse(d, raw)
        assert out["external_id"] == "req-9", out
        assert out["video_url"] == "https://cdn/v.mp4", out
        assert out["status"] == "succeeded", out
    check("named_fal_parse", t_named_fal_parse)

    def t_named_replicate_bytematch():
        nt = named_transforms.get_named_transform("replicate")
        d = ProviderDef(named_provider="replicate", model_default="wan-video/wan-2.2",
                        transform_type=TransformType.NAMED_PROVIDER)
        env = {"tenant_id": "t1", "prompt": "boat",
               "params": {"duration_s": 5, "aspect_ratio": "16:9", "resolution": "720p"}}
        url, headers, body = nt.build(d, "RTOK", env)
        brief = VideoBrief.from_any({"tenant_id": "t1", "prompt": "boat", "duration_s": 5,
                                     "aspect_ratio": "16:9", "resolution": "720p"})
        g = golden_providers.build_submit("replicate", brief, "wan-video/wan-2.2", "RTOK", "")
        assert (url, headers, body) == g, f"replicate drift: {(url, headers, body)} != {g}"
    check("named_replicate_bytematch_golden", t_named_replicate_bytematch)

    def t_named_luma_bytematch():
        nt = named_transforms.get_named_transform("luma")
        d = ProviderDef(named_provider="luma", model_default="ray-2",
                        transform_type=TransformType.NAMED_PROVIDER)
        env = {"tenant_id": "t1", "prompt": "sunset",
               "params": {"aspect_ratio": "1:1", "resolution": "720p"}}
        url, headers, body = nt.build(d, "LKEY", env)
        brief = VideoBrief.from_any({"tenant_id": "t1", "prompt": "sunset",
                                     "aspect_ratio": "1:1", "resolution": "720p"})
        g = golden_providers.build_submit("luma", brief, "ray-2", "LKEY", "")
        assert (url, headers, body) == g, f"luma drift: {(url, headers, body)} != {g}"
    check("named_luma_bytematch_golden", t_named_luma_bytematch)

    def t_named_text_anthropic():
        nt = named_transforms.get_named_transform("anthropic")
        assert nt is not None
        d = ProviderDef(named_provider="anthropic", base_url="https://api.anthropic.com",
                        model_default="claude-3-5-sonnet", transform_type=TransformType.NAMED_PROVIDER)
        url, headers, body = nt.build(d, "ak", {"prompt": "hi", "params": {"max_tokens": 10}})
        assert url == "https://api.anthropic.com/v1/messages", url
        assert headers["x-api-key"] == "ak"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        out = nt.parse(d, {"content": [{"type": "text", "text": "yo"}],
                           "usage": {"input_tokens": 2, "output_tokens": 1}})
        assert out["text"] == "yo" and out["status"] == "succeeded"
    check("named_anthropic_roundtrip", t_named_text_anthropic)

    def t_named_unknown():
        # an unregistered named provider yields an empty build + failed parse (never raises)
        d = ProviderDef(named_provider="does-not-exist", transform_type=TransformType.NAMED_PROVIDER)
        url, headers, body = adapter.build_request(d, "k", {"prompt": "x"})
        assert (url, headers, body) == ("", {}, {})
        out = adapter.parse_response(d, {"x": 1})
        assert out["status"] == "failed"
    check("named_unknown_failclosed", t_named_unknown)

    # ===================== Tier 3: custom_field_map (JSONPath, no-eval) =======
    def t_custom_build_apply():
        d = ProviderDef(base_url="https://vendor.example.com/gen",
                        auth_scheme=AuthScheme.BEARER, transform_type=TransformType.CUSTOM_FIELD_MAP,
                        request_field_map={"$.prompt": "$.input.text",
                                           "$.params.duration_s": "$.input.seconds"})
        env = {"prompt": "fox", "params": {"duration_s": 8}}
        url, headers, body = adapter.build_request(d, "vk", env)
        assert url == "https://vendor.example.com/gen", url
        assert headers["Authorization"] == "Bearer vk"
        assert body == {"input": {"text": "fox", "seconds": 8}}, body
    check("custom_fieldmap_build", t_custom_build_apply)

    def t_custom_parse_apply():
        d = ProviderDef(transform_type=TransformType.CUSTOM_FIELD_MAP,
                        response_field_map={"video_url": "$.data.output[0]",
                                            "external_id": "$.id"})
        raw = {"id": "j-7", "data": {"output": ["https://cdn/out.mp4"]}}
        out = adapter.parse_response(d, raw)
        assert out["video_url"] == "https://cdn/out.mp4", out
        assert out["external_id"] == "j-7", out
        assert out["status"] == "succeeded"
    check("custom_fieldmap_parse", t_custom_parse_apply)

    def t_validate_good():
        assert adapter.validate_field_map({"$.a.b": "$.x[0]", "$.c": "$['d']"}) is True
        assert adapter.validate_field_map(None) is True
        assert adapter.validate_field_map({}) is True
    check("validate_good_jsonpath", t_validate_good)

    def t_refuse_eval_and_garbage():
        # The SECURITY assertions: eval/template/wildcard/recursive/over-depth strings REFUSED.
        bad_cases = [
            {"$.a": "__import__('os').system('rm -rf /')"},   # eval-ish
            {"$.a": "{{ config.SECRET }}"},                    # jinja template
            {"$.a": "$..token"},                               # recursive descent
            {"$.a": "$.items[*].x"},                           # wildcard
            {"$.a": "$.a.b.c.d.e.f.g"},                         # over MAX_PATH_DEPTH
            {"a.b": "$.x"},                                     # missing leading $
            {"$.a": "$.b; DROP TABLE x"},                       # injection chars
            {"$.a": "$.b['unclosed"},                           # malformed
        ]
        for bad in bad_cases:
            try:
                adapter.validate_field_map(bad)
                raise AssertionError(f"validate_field_map ACCEPTED unsafe map: {bad}")
            except FieldMapError:
                pass  # expected
    check("refuse_eval_and_garbage", t_refuse_eval_and_garbage)

    def t_parse_jsonpath_depth():
        # exactly depth 5 ok; 6 refused
        adapter.parse_jsonpath("$.a.b.c.d.e")
        try:
            adapter.parse_jsonpath("$.a.b.c.d.e.f")
            raise AssertionError("depth 6 should be refused")
        except FieldMapError:
            pass
    check("jsonpath_depth_limit", t_parse_jsonpath_depth)

    def t_read_missing_returns_none():
        assert adapter._jsonpath_read({"a": {"b": 1}}, "$.a.z") is None
        assert adapter._jsonpath_read({"a": [1, 2]}, "$.a[5]") is None
        assert adapter._jsonpath_read({"a": [1, 2]}, "$.a[-1]") == 2
    check("jsonpath_read_missing", t_read_missing_returns_none)

    return _report("ADAPTER", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_adapter_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
