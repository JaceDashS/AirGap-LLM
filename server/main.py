from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
from typing import List

from gatekeeper import mask, restore
from router import ROUTER_SYSTEM_PROMPT, EASY_SYSTEM_PROMPT, COT_SYSTEM_PROMPT

app = FastAPI(title="AirGap LLM")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE = "http://localhost:11434"

# Generator maintains chat history (both easy and hard responses are saved here)
# CoT reasoning steps are NOT saved here — they are internal only
generator_history: List[dict] = []


class ChatRequest(BaseModel):
    message: str
    model: str


async def ollama_chat(prompt: str, model: str, system: str | None = None) -> str:
    """Stateless single-turn call to Ollama."""
    payload = {"model": model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            res = await client.post(f"{OLLAMA_BASE}/api/generate", json=payload)
            res.raise_for_status()
            return res.json()["response"]
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ollama is not running. Start it with: ollama serve")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


async def run_cot(prompt: str, model: str) -> str:
    """
    CoT step — isolated context, result is NOT saved to generator_history.
    Asks the model to reason step by step and return its reasoning.
    The reasoning result is then passed to the Generator as additional context.
    """
    return await ollama_chat(prompt, model, system=COT_SYSTEM_PROMPT)


async def run_generator(prompt: str, model: str, cot_reasoning: str | None = None) -> str:
    """
    Generator — maintains chat history.
    If cot_reasoning is provided (hard path), it is injected as context but NOT saved to history.
    Only the final user prompt and assistant response are saved to generator_history.
    """
    global generator_history

    # Build prompt: inject CoT reasoning as silent context if available
    if cot_reasoning:
        full_prompt = (
            f"[Internal reasoning — not part of conversation]\n{cot_reasoning}\n\n"
            f"[User question]\n{prompt}"
        )
    else:
        full_prompt = prompt

    # Append history turns to prompt
    history_prompt = ""
    for turn in generator_history:
        role = "User" if turn["role"] == "user" else "Assistant"
        history_prompt += f"{role}: {turn['content']}\n"
    history_prompt += f"User: {full_prompt}\nAssistant:"

    response = await ollama_chat(history_prompt, model, system=EASY_SYSTEM_PROMPT)

    # Save only the original user prompt and final response to history (not CoT)
    generator_history.append({"role": "user", "content": prompt})
    generator_history.append({"role": "assistant", "content": response})

    return response


async def route_query(prompt: str, model: str) -> dict:
    """
    Ask the model to classify the prompt difficulty.
    Returns {"difficulty": "easy"|"hard", "reason": "..."}
    Falls back to "easy" if parsing fails.
    """
    raw = await ollama_chat(prompt, model, system=ROUTER_SYSTEM_PROMPT)

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        difficulty = result.get("difficulty", "easy").lower()
        if difficulty not in ("easy", "hard"):
            difficulty = "easy"
        return {"difficulty": difficulty, "reason": result.get("reason", "")}
    except (ValueError, json.JSONDecodeError):
        return {"difficulty": "easy", "reason": "Could not parse router response, defaulted to easy."}


@app.get("/models")
async def get_models():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.get(f"{OLLAMA_BASE}/api/tags")
            res.raise_for_status()
            models = [m["name"] for m in res.json().get("models", [])]
            return {"models": models}
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ollama is not running. Start it with: ollama serve")


@app.post("/chat/gated")
async def chat_gated(req: ChatRequest):
    # Step 1 — mask PII using LLM gatekeeper
    masked_input, vault = await mask(req.message, req.model)

    # Step 2 — router decides difficulty
    routing = await route_query(masked_input, req.model)
    difficulty = routing["difficulty"]

    # Step 3 — hard: run CoT first (isolated, not saved to history), then pass reasoning to Generator
    #           easy: skip CoT, go straight to Generator
    cot_reasoning = None
    if difficulty == "hard":
        cot_reasoning = await run_cot(masked_input, req.model)

    # Step 4 — Generator produces final response (saves to history, CoT reasoning is not saved)
    llm_response = await run_generator(masked_input, req.model, cot_reasoning=cot_reasoning)

    # Step 5 — restore PII in the response
    restored_response = restore(llm_response, vault)

    return {
        "response": restored_response,
        "masked_input": masked_input,
        "vault": vault,
        "routing": {
            "difficulty": difficulty,
            "reason": routing["reason"],
            "model": req.model,
            "mode": "chain-of-thought" if difficulty == "hard" else "direct",
        },
        "cot_reasoning": cot_reasoning,
    }


@app.post("/chat/direct")
async def chat_direct(req: ChatRequest):
    """Direct access to Generator — no gatekeeper, no router. PII is fully exposed."""
    llm_response = await run_generator(req.message, req.model)
    return {
        "response": llm_response,
    }


@app.post("/chat/reset")
async def reset_history():
    """Clear the Generator's chat history."""
    global generator_history
    generator_history = []
    return {"status": "Generator history cleared"}
