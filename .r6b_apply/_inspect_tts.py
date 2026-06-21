import inspect
try:
    import livekit.agents as a
    print("VER", getattr(a, "__version__", "?"))
except Exception as e:
    print("IMPORT_ERR", e)
try:
    from livekit.agents import Agent
    print("=== tts_node signature ===")
    print(inspect.signature(Agent.tts_node))
    src = inspect.getsource(Agent.tts_node)
    print(src[:1400])
except Exception as e:
    print("TTS_NODE_ERR", e)
