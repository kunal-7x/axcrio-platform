# PERF UNIT-2 — CRM DETAIL SPEEDUP + recordings playable-flag (STATE)

Box famit@168.144.153.145 ; caller :8209 ; venv /opt/capsy-agent/.venv ; deploy /opt/famit-agent.
EARNER GATE BASELINE (must stay): agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 ; famit-agent MainPID 1477083 ; ActiveEnter 2026-06-10 19:58:18.
Box+local baseline md5 (PRE-unit2): caller d96fafc9910891b6b235cd8df6d68ff4 ; crm/core 934872dc5e435a880e0b041caca9e63f ; recorder 0d716d190b9f10b5d242e014dec1de89.

## PLAN (additive, isolated, caller-only restart)
### Part 1 — CRM detail speedup (crm/core.py + caller.py contacts_get)
- ROOT: contacts_get -> project_contact(rebuild=True) does an UNCONDITIONAL full rebuild_timeline
  (PG scan of all call rows + N+1 transcript DISK reads + re-INSERTs) on EVERY lead open, then
  project does _lead_for + get_timeline(500) + suppression + override SELECT + UPDATE (serial),
  THEN route calls get_timeline(50) AGAIN + next_best_action. Multi-roundtrip + full rebuild/read.
- NO live-append path exists (rebuild_timeline is the ONLY writer of contact_timeline). So can't
  literally "rebuild on write" without touching the earner write path -> instead:
  FRESHNESS-GATED rebuild + dedup the redundant timeline read + parallelize.
  (1) project_contact(rebuild=...): skip rebuild when a process-local TTL cache says this contact
      was rebuilt < TTL ago (default 90s). Force-rebuild path stays for backfill/smoke (rebuild=True).
  (2) contacts_get: project WITHOUT the second get_timeline(500) feeding a redundant get_timeline(50);
      reuse ONE timeline read. Run the independent reads concurrently with asyncio.gather/to_thread.
  (3) project_contact returns the timeline it already read so the route doesn't re-query.
- Net: a 2nd+ open of the same lead within TTL = fast cached read (no rebuild, no N+1 disk reads).

### Part 2 — recordings playable-flag (recorder.head_object + _outbound_rec_item)
- ROOT: outbound auto-egress OGGs can be near-empty/486-busy -> duration shows, bytes don't decode.
- FIX: recorder.head_object(bucket,key) -> {exists,size,content_type} via the SAME boto3 client as
  presign. In _outbound_rec_item: HEAD-verify BEFORE presign; add `playable:bool` + `size_bytes` to the
  item; omit recording_presigned_url when not playable. Threshold: size >= MIN_PLAYABLE_OGG_BYTES (2048)
  AND content-type audio/* (or .ogg key). Inbound REC-A already finalize-gated; also stamp playable there.
- FE contract: render <audio> ONLY when item.playable===true && recording_presigned_url; else "preparing".

## PROGRESS — COMPLETE + SHIPPED LIVE + VERIFIED
- [x] baseline captured, files match box
- [x] Part 1 code (freshness-gated rebuild + reuse timeline + inline NBA)
- [x] Part 2 code (recorder.head_object + _rec_playable gate + playable/size_bytes)
- [x] py_compile local + box venv (BOX_PYCOMPILE_OK)
- [x] backups PERFbak.20260614-004718 + md5-gated scp + restart famit-caller ONLY
- [x] EARNER GATE re-verify PASS (agent.py md5 9150fabe UNCHANGED; MainPID 1477083; ActiveEnter unchanged; 3 svc active; /health 200)
- [x] live smoke: CRM open#1 129ms -> open#2 (TTL-cached) 33ms ~4x; no _timeline leak; recordings 5 real OGG playable+url, disabled none; _rec_playable proven REAL/FAKE/TINY/octet/nonaudio
- [x] commit

## POST md5
box+local: caller 474c6a405a633f3aef97782c25a489d8 ; crm/core 3b3de323e717338af1eb31ea7c3c5af0 ; recorder 7e3716918294b1b2ae3c6d221aedfb0a

## FE CONTRACT (for the panel wave)
- /contacts/{phone}: unchanged shape {contact, timeline(<=50), nba} — now fast on repeat opens (no internal change to FE needed; just faster).
- /contacts/{phone}/recordings AND /calls/{id}/recording items now carry: `playable:bool`, `size_bytes:int`.
  Render <audio> ONLY when item.playable===true && item.recording_presigned_url. Else show "preparing"/disabled.
  contact_recordings adds top-level `with_playable:int`.
