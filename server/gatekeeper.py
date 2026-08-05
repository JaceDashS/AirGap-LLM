import json
import httpx

OLLAMA_BASE = "http://localhost:11434"

MASK_SYSTEM_PROMPT = """You are a PII (Personally Identifiable Information) detection and masking assistant.
Your job is to find all sensitive information in the user's text and replace each one with a unique token.

Sensitive information includes but is not limited to:
- URLs and API endpoints (e.g. https://api.example.com/v1/users)
- Email addresses
- Phone numbers
- Names of real people
- Physical addresses
- API keys, tokens, passwords
- Any other information that could identify a person or expose internal systems

Rules:
- Assign each piece of sensitive information a unique token in the format [PII_<TYPE>_<N>] where TYPE is a short uppercase label (e.g. URL, EMAIL, NAME, KEY) and N is a number starting from 1.
- If the same value appears multiple times, reuse the same token.
- Return ONLY a JSON object with two fields, nothing else:
  {
    "masked_text": "the full original text with PII replaced by tokens",
    "vault": {
      "[PII_URL_1]": "https://api.example.com/v1/users",
      "[PII_EMAIL_1]": "john@example.com"
    }
  }
- If no PII is found, return the original text unchanged and an empty vault: {"masked_text": "<original>", "vault": {}}
"""


async def mask(text: str, model: str) -> tuple[str, dict[str, str]]:
    """
    Use an LLM to detect and mask PII in the text.
    Returns (masked_text, vault) where vault maps token -> original value.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": text,
                "system": MASK_SYSTEM_PROMPT,
                "stream": False,
            },
        )
        res.raise_for_status()
        raw = res.json()["response"]

    # Extract JSON from response (LLM may wrap in markdown)
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        masked_text = result.get("masked_text", text)
        vault = result.get("vault", {})
        return masked_text, vault
    except (ValueError, json.JSONDecodeError):
        # If parsing fails, return original text with empty vault (fail-safe)
        return text, {}


def restore(text: str, vault: dict[str, str]) -> str:
    """
    Replace all tokens in text with their original values from the vault.
    """
    for token, original in vault.items():
        text = text.replace(token, original)
    return text
