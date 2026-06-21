import inspect
import livekit.plugins.groq as g
print("GROQ_FILE", g.__file__)
print("LLM_SIG", str(inspect.signature(g.LLM.__init__)))
import livekit.agents.llm as al
print("HAS_FB", hasattr(al, "FallbackAdapter"))
fb = al.FallbackAdapter
print("FB_SIG", str(inspect.signature(fb.__init__)))
