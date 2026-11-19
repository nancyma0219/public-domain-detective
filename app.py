"""Public Domain Detective: FastAPI app.

POST /chat     {"message", "session_id"?} -> {"response", "session_id", "tool_calls": [{agent, name, arguments, output}], ...}
GET  /stream   the same investigation as Server-Sent Events, for the web page (live activity + context panel)
GET  /         the web page
"""

import threading
import webbrowser

import asyncio
import json
import os
import uuid
from pathlib import Path

import uvicorn
from agents import set_tracing_disabled
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")
set_tracing_disabled(True)  # traces upload to OpenAI by default; we're on Gemini

from context_panel import AgentContexts, add_context_panel  # noqa: E402
from research import investigate  # noqa: E402

HERE = Path(__file__).parent
app = FastAPI(title="Public Domain Detective")

chats: dict[str, list[dict]] = {}   # session_id -> conversation turns ({role, content}), in memory
panels: dict[str, AgentContexts] = {}  # run_id -> every agent's context, read by the context panel
add_context_panel(app, panels)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


def _remember(session_id: str, message: str, result: dict) -> None:
    history = chats.setdefault(session_id, [])
    history += [{"role": "user", "content": message}, {"role": "assistant", "content": result["response"]}]
    del history[:-8]  # the last 4 exchanges: enough for a clarification round-trip


@app.post("/chat")
async def chat(req: ChatRequest):
    """Project 1's /chat shape: the answer plus every tool call, each tagged with the agent that made it."""
    session_id = req.session_id or str(uuid.uuid4())
    try:
        result = await investigate(req.message, list(chats.get(session_id, [])))
    except Exception as e:
        return {"response": f"The investigation failed: {type(e).__name__}: {str(e)[:500]}",
                "session_id": session_id, "tool_calls": [], "error": True}
    _remember(session_id, req.message, result)
    return {"session_id": session_id, **result}


@app.get("/stream")
async def stream(message: str, session_id: str | None = None):
    session_id = session_id or str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    panels[run_id] = AgentContexts()
    queue: asyncio.Queue = asyncio.Queue()

    async def work():
        try:
            result = await investigate(message, list(chats.get(session_id, [])), emit=queue.put_nowait,
                                       contexts=panels[run_id])
            _remember(session_id, message, result)
            queue.put_nowait({"type": "done", "session_id": session_id, **result})
        except Exception as e:  # auth, quota, a model that won't stop: show it on the page
            queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {str(e)[:500]}"})

    task = asyncio.create_task(work())

    async def events():
        try:
            yield f"data: {json.dumps({'type': 'start', 'run_id': run_id, 'session_id': session_id})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event["type"] in ("done", "error"):
                    break
        finally:
            task.cancel()  # the page closed the stream: stop spending tokens

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse(HERE / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz():
    return {"ok": True}


# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    # Automatically open the browser during local development.
    # Do not open a browser when deployed to Cloud Run.
    if not os.environ.get("K_SERVICE"):
        threading.Timer(
            1.5,
            lambda: webbrowser.open(f"http://127.0.0.1:{port}")
        ).start()

    uvicorn.run(app, host="0.0.0.0", port=port)