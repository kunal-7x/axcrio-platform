import hashlib
src = open(r"C:\Users\kunal\Desktop\caps\.r6b_apply\agent.py", encoding="utf-8").read()
lines = src.splitlines(keepends=True)
def span_md5(start_anchor, end_anchor):
    i = next(k for k,l in enumerate(lines) if start_anchor in l)
    j = next(k for k,l in enumerate(lines) if end_anchor in l and k>=i)
    blob = "".join(lines[i:j+1])
    return hashlib.md5(blob.encode("utf-8")).hexdigest(), i+1, j+1
print("EL", span_md5("tts = elevenlabs.TTS(", "auto_mode=True,"))
print("STTLLM", span_md5("stt=sarvam.STT(", "max_completion_tokens=int(os.getenv"))
