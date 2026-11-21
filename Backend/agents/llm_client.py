"""Small, bounded ADK runner; no fallback pretending to be a live agent."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


logger = logging.getLogger("queueguard.agents")
BACKEND_PATH = Path(__file__).resolve().parents[1]
Rating = Annotated[int, Field(strict=True, ge=0, le=5)]


class AgentError(RuntimeError):
    """Integration must mark this ticket needs_review and audit the failure."""


class AnalysisResult(BaseModel):
    """Local wire schema until Person 1 supplies core.models dataclasses."""

    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["authentication", "network", "database", "hardware",
                      "software", "security", "other"]
    service_id: Literal["auth", "web", "db", "unknown"]
    impact: Rating
    urgency: Rating
    affected_scope: Rating
    sla_risk: Rating
    duplicate_ids: list[Annotated[int, Field(strict=True, gt=0)]]
    checked_evidence: list[dict]
    reasoning: str = Field(min_length=1, max_length=8000)
    missing_information: list[str]


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_status: Literal["confirmed", "unverified", "conflicting"]
    injection_suspected: bool
    injection_reasons: list[str]
    conflicting_facts: list[str]
    recommended_status: Literal["open", "needs_review", "reject"]
    explanation: str = Field(min_length=1, max_length=8000)


@dataclass
class ADKResult:
    output: dict
    tool_responses: list[dict]


def run_sync(async_function, *args):
    """Support the agreed sync API, even when called from a FastAPI loop.

    Async routes should prefer await agent.analyze_async(ticket) so the route
    does not block. Each invocation creates its own runner and session.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        in_event_loop = False
    else:
        in_event_loop = True
    if in_event_loop:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(async_function(*args))).result()
    return asyncio.run(async_function(*args))


def load_configuration() -> str:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_PATH / ".env", override=False)
    if os.getenv("QUEUEGUARD_DEMO_MODE", "").strip().lower() in {"1", "true", "yes"}:
        return "queueguard-offline-demo"
    if not os.getenv("GOOGLE_API_KEY"):
        alias = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")
        if alias:
            os.environ["GOOGLE_API_KEY"] = alias
    if not os.getenv("GOOGLE_API_KEY"):
        raise AgentError("GOOGLE_API_KEY fehlt; Ticket auf needs_review setzen.")
    return os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def ticket_payload(ticket: dict) -> dict:
    """Only forward ticket data, never credentials or backend control fields."""
    if not isinstance(ticket, dict):
        raise AgentError("Ticket muss ein Dictionary sein.")
    result = {}
    for key in ("title", "description", "reported_priority"):
        value = ticket.get(key, "")
        if not isinstance(value, str) or len(value) > 16000:
            raise AgentError("Ungueltiges Ticketfeld: " + key)
        result[key] = value
    if not (result["title"].strip() or result["description"].strip()):
        raise AgentError("Ticket braucht Titel oder Beschreibung.")
    return result


async def run_adk(*, name: str, instruction: str, payload: dict,
                  tools: list, model=None, timeout: float = 45) -> ADKResult:
    """Execute real ADK FunctionTools and capture their response events.

    A BaseLlm may be injected by offline tests. Normal calls always use Gemini.
    We ask for JSON in the prompt rather than force a response MIME type while
    tools are active, to remain compatible with Gemini function calling.
    """
    from google.adk.agents import LlmAgent
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.models.google_llm import Gemini
    from google import genai
    from google.genai import types

    if model is None or isinstance(model, str):
        configured_model = load_configuration()
        model = model or configured_model
    if model == "queueguard-offline-demo":
        from .demo_model import DemoModel

        logger.warning("OFFLINE_DEMO agent=%s simulated_model_no_gemini", name)
        model = DemoModel(role=name)
    allowed_tools = {tool.__name__ for tool in tools}

    async def execute():
        # Runner.close() does not close model HTTP clients in ADK 2.15.
        # Own the client explicitly so sync calls do not leave sockets tied to
        # an event loop which asyncio.run() is about to close on Windows.
        client = None
        active_model = model
        if isinstance(model, str):
            client = genai.Client(http_options=types.HttpOptions(
                timeout=int(timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ))
            active_model = Gemini(model=model, client=client)
        agent = LlmAgent(
            name=name, model=active_model, instruction=instruction, tools=tools,
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )
        sessions = InMemorySessionService()
        session_id = uuid4().hex
        await sessions.create_session(app_name="queueguard", user_id="backend",
                                      session_id=session_id)
        runner = Runner(agent=agent, app_name="queueguard", session_service=sessions)
        responses = []
        pending = {}
        final_text = ""
        try:
            async for event in runner.run_async(
                user_id="backend", session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part.from_text(
                    text="UNTRUSTED_INPUT_JSON\n" + json.dumps(payload, ensure_ascii=False)
                )]),
                run_config=RunConfig(max_llm_calls=8),
            ):
                for call in event.get_function_calls():
                    if call.name not in allowed_tools:
                        raise AgentError("Nicht erlaubter Tool-Aufruf; needs_review.")
                    pending[call.id] = call.name
                    logger.info("ADK_TOOL_CALL name=%s", call.name)
                for response in event.get_function_responses():
                    if pending.get(response.id) != response.name:
                        raise AgentError("Tool-Antwort ohne passenden Aufruf; needs_review.")
                    pending.pop(response.id)
                    responses.append({"tool": response.name, "result": response.response})
                    logger.info("ADK_TOOL_RESULT name=%s", response.name)
                if event.is_final_response() and event.content:
                    final_text = "".join(
                        part.text or "" for part in event.content.parts if not part.thought
                    )
            if pending:
                raise AgentError("Tool-Aufruf ohne Ergebnis; needs_review.")
            clean = final_text.strip()
            if clean.startswith("```json") and clean.endswith("```"):
                clean = clean[7:-3].strip()
            elif clean.startswith("```") and clean.endswith("```"):
                clean = clean[3:-3].strip()
            output = json.loads(clean)
            if not isinstance(output, dict):
                raise AgentError("Agent lieferte kein JSON-Objekt; needs_review.")
            return ADKResult(output=output, tool_responses=responses)
        finally:
            try:
                await runner.close()
            finally:
                try:
                    await sessions.delete_session(app_name="queueguard", user_id="backend",
                                                  session_id=session_id)
                finally:
                    if client is not None:
                        try:
                            await client.aio.aclose()
                        finally:
                            client.close()

    try:
        return await asyncio.wait_for(execute(), timeout=timeout)
    except AgentError:
        raise
    except Exception as exc:
        # Never log exception text: SDK errors may contain prompt data or keys.
        status = getattr(exc, "code", None)
        logger.warning("ADK_FAILED agent=%s error_type=%s http_status=%s",
                       name, type(exc).__name__, status)
        raise AgentError(
            f"ADK-Aufruf fehlgeschlagen ({type(exc).__name__}, HTTP {status}); needs_review."
        ) from None
