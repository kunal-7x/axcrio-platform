# Integration-Seam Design Note — context subsystem (DO NOT edit live files in this wave)

Scope: how the W1/W3 context subsystem + the W-RED injection fix wire into the
LIVE path LATER, behind a flag. This wave builds + tests the module and WRITES
this note; it does NOT edit `droplet_work/agent.py` (md5 98655dbf, FROZEN),
`caller.py`, or `aim_voice_agent.py`.

## 1. The /extract + run_job + recap seam (flag-gated, LATER)
- SAVE-TIME (`caller.py` campaign save / `extract_fields`): when a vendor saves a
  campaign, call `compile_campaign(tenant_id, campaign_id, brief=raw_brief,
  fields=extracted)` and persist the `CompiledCampaign` (the T0 lossless fenced
  brief + T2 compact card + understanding). Register the vendor script via
  `VendorScriptEngineImpl.register(campaign_id, raw_script, variables=...)`.
  This REPLACES the lossy ~4k JSON compression (caller.py:1372/1409) — the full
  brief is preserved, the in-prompt copy is a flagged compact summary.
- DIAL-TIME (`agent.py` prefix build, currently the ~13k f-string): behind
  `KERNEL_CONTEXT_ENABLED`, build the prefix via
  `build_kernel(cfg, context=ce, vendor_script=vs).assemble_prefix_core(ctx)`,
  passing `safety_rules=prompt.SHARED_RULES` VERBATIM as L0. Default OFF =
  byte-identical to today (proven by the W1 parity matrix). The KernelSession is
  SERVER-STAMPED from the resolved campaign owner, never the dispatch body.
- RECAP seam (lead memory): `MemoryService.load(tenant_id, lead_phone)` at dial,
  `persist(...)` post-call. The recap string today becomes the structured
  `LeadMemory` (L4), rendered in a LEAD_MEMORY fence.

## 2. RED-TEAM residual to harden at the seam (defense-in-depth)
The render choke point (`packet.FencedText.render` -> `defang_fences`) now
neutralizes forged fence tags from ANY untrusted source for the PROMPT. Two
upstream hardening adds, for the seam wave (NOT blockers, the prompt is already
safe):

  (a) `voice_kernel/rag/ingest.py` does NOT `sanitize()` the extracted PDF/text
      before `corpus.ingest(...)`. ADD `text = sanitize(text)` after `_extract`
      (import from `..context.text_hygiene`). Rationale: keep the STORED corpus
      clean for every consumer (not only the prompt), and strip zero-width /
      control chars at the boundary. The prompt path is already safe via the
      render defang, so this is belt-and-suspenders, schedulable, low-risk.

  (b) The LIVE CALLER UTTERANCE (STT output) is the 5th untrusted source. When the
      seam feeds the live transcript into the turn context, wrap it as
      `fence(SourceTrust.CALLER_UTTERANCE, stt_text)` — the renderer already
      defangs it. Do NOT interpolate raw STT into the prompt unfenced.

## 3. Trust-boundary invariant the seam MUST preserve
L0 (identity + `SHARED_RULES`) is PLATFORM, rendered FIRST by position, NEVER
fenced. Everything else (campaign brief L3, RAG L5, lead memory L4, caller
utterance) is UNTRUSTED, carried as `FencedText`, rendered BELOW L0. The seam
must pass `SHARED_RULES` as L0 and must NEVER promote any vendor/RAG/memory/STT
text above it. The render choke point enforces "can't break out of the fence";
position enforces "safety is first". Both are required.

## 4. What is proven NOW (this wave)
- All 4 canonical attacks (ignore rules / quote FREE / reveal prompt / collect
  card) across all 4 untrusted vectors (brief / vendor-script / RAG-PDF /
  lead-memory) are STRUCTURALLY NEUTRALIZED on a normal assembled call:
  fences stay balanced (1 open / 1 close), payload stays positionally below the
  platform safety layer. Test: `voice_kernel/tests/test_redteam_injection.py` (9/9).
- The kernel claims structural containment (payload can't reach instruction
  altitude), NOT that the LLM is un-jailbreakable — refusal is the model's job,
  containment is the kernel's. The seam should keep an eval probe on the live model.
