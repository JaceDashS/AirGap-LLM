# AirGap LLM

## Purpose

This project simulates how a **third-party AI provider** can reduce the exposure of sensitive user data while still using a language model.

The Gated path detects sensitive strings, replaces them with neutral placeholders, processes the masked request, and restores the original values only when presenting the result to the user.

This is a **local educational simulation**, not a production security control.

## How It Works

### Gated Path

```text
User → Router → PII Detector → Masking → (optional Reasoning) → Generator → Restore → User
```

1. The **Router** classifies the request as `instant` or `reasoning`.
2. The **PII Detector** returns exact strings to replace.
3. **Masking Logic** replaces them with neutral placeholders (e.g. `[[PII_000001]]`) and records mappings in the **Session Vault**.
4. Optional **Reasoning** runs a step-by-step trace (not saved to history) when the Router selects `reasoning`.
5. The **Generator** produces a response against the masked input only — it never sees the original values.
6. **Restore Logic** replaces placeholders in the streamed response with their original values before presenting to the user.

### Direct Path

```text
User → Generator → User
```

The message is sent straight to the Generator with no PII detection, no masking, and no restoration. The LLM receives all sensitive information as-is. This path exists for educational comparison only.

## Architecture Notes

- All four LLM roles (Router, PII Detector, Reasoning, Generator) share the same Ollama model weights but run in **isolated contexts** — none sees another's history.
- The **Session Vault** persists for the duration of the server process. Committed placeholder mappings are never deleted and numbers are never reused.
- Vault matching is **exact and case-sensitive**. Different capitalisation or whitespace for the same real-world entity creates separate entries.
- The server enforces a **global busy lock** — one active request at a time.
- All streamed responses use **NDJSON** (`application/x-ndjson`).

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally

## Setup

### 1. Install Ollama and pull a model

```bash
ollama pull llama3.2
```

### 2. Install Python dependencies

```bash
cd server
pip install -r requirements.txt
```

### 3. Start the server

```bash
cd server
uvicorn main:app --reload --port 8000
```

### 4. Open the client

Open `client/index.html` directly in your browser.

The client calls `http://localhost:8000` by default.

## Status

| Task | Description | Status |
|---|---|---|
| Task 1 | Project Scaffold | ✅ done |
| Task 2 | Gatekeeper Module | ⬜ pending |
| Task 3 | FastAPI Server | ⬜ pending |
| Task 4 | Interactive Frontend UI | ⬜ pending |
| Task 5 | Model Selection and Prompt Tuning | ⬜ pending |
