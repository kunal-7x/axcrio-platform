from livekit.agents.llm import ChatChunk
print("fields:", list(ChatChunk.model_fields))
c = ChatChunk(id="x")
print("ok:", repr(c)[:120])
