"""set_sarvam_model.py — flip the live Sarvam chat model id in /data/voice_keys.json.

Changes ONLY `sarvam_model` (and ensures llm_provider=sarvam); the existing Sarvam
API key is preserved untouched. Backs up to voice_keys.json.bak-sarvammodel.

Usage (inside the worker/backend container):
    python set_sarvam_model.py sarvam-30b
    python set_sarvam_model.py sarvam-105b   # revert
"""
import json
import shutil
import sys

PATH = "/data/voice_keys.json"


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "sarvam-30b"
    with open(PATH) as fh:
        cfg = json.load(fh)

    # Never break the live agent: refuse to switch if no Sarvam key is present.
    if not (cfg.get("sarvam_llm_api_key") or cfg.get("sarvam_api_key")):
        print("ABORT: no Sarvam key (sarvam_llm_api_key) in voice_keys.json — not switching.")
        return 1

    shutil.copy(PATH, PATH + ".bak-sarvammodel")
    cfg["llm_provider"] = "sarvam"
    cfg["sarvam_model"] = model
    with open(PATH, "w") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)

    print(f"OK: provider=sarvam, sarvam_model={cfg['sarvam_model']} (key preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
