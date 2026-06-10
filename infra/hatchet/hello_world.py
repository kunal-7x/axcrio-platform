"""F3 Hatchet hello-world — proves durable execution end-to-end on famit-hatchet.

Runs ON THE BOX (worker + trigger over localhost gRPC 127.0.0.1:7077, insecure).
Env required (set before run):
  HATCHET_CLIENT_TOKEN=<from hatchet-admin token create>
  HATCHET_CLIENT_HOST_PORT=127.0.0.1:7077
  HATCHET_CLIENT_TLS_STRATEGY=none

Usage:
  python hello_world.py worker     # start the worker (registers the workflow), runs forever
  python hello_world.py trigger    # trigger one run and print the result (worker must be up)
"""
import sys
from pydantic import BaseModel
from hatchet_sdk import Hatchet

hatchet = Hatchet()


class HelloInput(BaseModel):
    name: str = "World"


hello_wf = hatchet.workflow(name="f3-hello-world", input_validator=HelloInput)


@hello_wf.task()
def greet(input: HelloInput, ctx) -> dict:
    msg = f"Hello, {input.name}! Hatchet F3 durable execution works."
    print("[task greet] ->", msg)
    return {"message": msg, "ok": True}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "worker"
    if mode == "worker":
        worker = hatchet.worker("f3-hello-worker", workflows=[hello_wf])
        worker.start()
    elif mode == "trigger":
        result = hello_wf.run(HelloInput(name="F3"))
        print("RUN RESULT:", result)
    else:
        print("usage: python hello_world.py [worker|trigger]")
        sys.exit(2)


if __name__ == "__main__":
    main()
