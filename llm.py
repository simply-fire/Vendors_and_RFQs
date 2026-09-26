import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

OPENROUTER_URL = os.environ.get(
    "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"
)
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "z-ai/glm-5.3-flash")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
HTTP_TIMEOUT = float(os.environ.get("OPENROUTER_TIMEOUT", "60"))

DIMENSIONS = {"technical", "mandatory", "required", "preferred", "logistics"}

SYSTEM_PROMPT = """\
You are an expert vendor-evaluation analyst for an aerospace and defence \
procurement team. Given an RFQ (Request for Quotation) and a vendor profile, \
score how well the vendor matches the RFQ.

HARD-GATE RULE: If the vendor fails to demonstrate ANY item listed in the \
MANDATORY section, the final score MUST be <=40, regardless of strengths \
elsewhere. The missing mandatory item MUST appear in the gaps.

Scoring dimensions (use these exact tags):
- technical   capabilities, tolerances, materials, processes
- mandatory   must-have certifications or approvals (HARD GATE)
- required    strongly expected items; missing counts against the score
- preferred   nice-to-have; missing noted as a gap
- logistics   quantity capacity and delivery timeline

Rules:
- Return exactly 3 reasons (positive evidence) and exactly 2 gaps.
- Every reason and gap MUST be tagged with one of the five dimensions above.
- Text must reference actual content from the vendor profile (specific facts, \
numbers, certifications) — never generic filler.
- If the vendor profile does not actually address a dimension, do not invent a \
reason for it; mention the absence in a gap if it is material to the RFQ.
"""

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_evaluation",
        "description": "Submit the structured vendor evaluation result.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Overall alignment score from 0 to 100.",
                },
                "reasons": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "text": {"type": "string", "minLength": 1},
                            "dimension": {
                                "type": "string",
                                "enum": [
                                    "technical",
                                    "mandatory",
                                    "required",
                                    "preferred",
                                    "logistics",
                                ],
                            },
                        },
                        "required": ["text", "dimension"],
                    },
                },
                "gaps": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "text": {"type": "string", "minLength": 1},
                            "dimension": {
                                "type": "string",
                                "enum": [
                                    "technical",
                                    "mandatory",
                                    "required",
                                    "preferred",
                                    "logistics",
                                ],
                            },
                        },
                        "required": ["text", "dimension"],
                    },
                },
            },
            "required": ["score", "reasons", "gaps"],
        },
    },
}


class LLMSchemaError(Exception):
    """LLM failed to produce a usable evaluation result.

    Raised after one retry on shape/schema failures, or immediately on
    transport failures (which we deliberately do not retry).
    """


class _TransportError(Exception):
    """HTTP / network / timeout from OpenRouter. Not retried."""


class _ShapeError(Exception):
    """LLM returned 200 but the response is not a usable tool call. Retried
    once (same call) per the project's 'one retry on bad LLM output' rule."""


def _build_user_prompt(rfq, vendor_text):
    lines = [
        f"RFQ id: {rfq['id']}",
        f"Title: {rfq['title']}",
        f"Category: {rfq['category']}",
        "",
        "Logistics:",
        f"- Quantity: {rfq['quantity']}",
        f"- Delivery: {rfq['delivery']}",
        "",
        "Technical requirements:",
        *[f"- {item}" for item in rfq["technical"]],
        "",
        "Mandatory (must-have; missing any caps score at 40):",
        *[f"- {item}" for item in rfq["mandatory"]],
        "",
        "Required (strongly expected):",
        *[f"- {item}" for item in rfq["required"]],
        "",
        "Preferred (nice-to-have):",
        *[f"- {item}" for item in rfq["preferred"]],
        "",
        "---",
        "Vendor profile:",
        vendor_text.strip(),
        "",
        "Call submit_evaluation with your verdict.",
    ]
    return "\n".join(lines)


def _call_openrouter(messages):
    body = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "tools": [TOOL_SCHEMA],
        "tool_choice": {
            "type": "function",
            "function": {"name": "submit_evaluation"},
        },
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Vendor RFQ Evaluator",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise _TransportError(f"OpenRouter HTTP {e.code}: {detail[:200]}")
    except urllib.error.URLError as e:
        raise _TransportError(f"OpenRouter connection error: {e.reason}")

    try:
        message = payload["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
    except (KeyError, IndexError, TypeError):
        raise _ShapeError("unexpected response shape from OpenRouter")

    if not tool_calls:
        raise _ShapeError("no tool_calls in response")

    args_str = tool_calls[0].get("function", {}).get("arguments")
    if not args_str:
        raise _ShapeError("no function arguments in tool_call")

    try:
        return json.loads(args_str)
    except json.JSONDecodeError as e:
        raise _ShapeError(f"function arguments not valid JSON: {e}")


def _validate(result):
    if not isinstance(result, dict):
        return f"result is not an object (got {type(result).__name__})"

    score = result.get("score")
    if (
        not isinstance(score, int)
        or isinstance(score, bool)
        or not 0 <= score <= 100
    ):
        return f"score must be int in 0..100, got {score!r}"

    reasons = result.get("reasons")
    if not isinstance(reasons, list):
        return f"reasons must be a list, got {type(reasons).__name__}"
    if len(reasons) != 3:
        return f"reasons must contain exactly 3 items, got {len(reasons)}"

    for i, r in enumerate(reasons):
        if not isinstance(r, dict):
            return f"reasons[{i}] is not an object"
        text = r.get("text")
        dim = r.get("dimension")
        if not isinstance(text, str) or not text.strip():
            return f"reasons[{i}].text is empty"
        if dim not in DIMENSIONS:
            return f"reasons[{i}].dimension invalid: {dim!r}"

    gaps = result.get("gaps")
    if not isinstance(gaps, list):
        return f"gaps must be a list, got {type(gaps).__name__}"
    if len(gaps) != 2:
        return f"gaps must contain exactly 2 items, got {len(gaps)}"

    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            return f"gaps[{i}] is not an object"
        text = g.get("text")
        dim = g.get("dimension")
        if not isinstance(text, str) or not text.strip():
            return f"gaps[{i}].text is empty"
        if dim not in DIMENSIONS:
            return f"gaps[{i}].dimension invalid: {dim!r}"

    return None


def evaluate_with_llm(rfq, vendor_text):
    if not OPENROUTER_API_KEY:
        raise LLMSchemaError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file "
            "(see .env.example) or export it before running the app."
        )

    user_prompt = _build_user_prompt(rfq, vendor_text)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_err = "unknown"

    for attempt in (1, 2):
        try:
            result = _call_openrouter(messages)
        except _TransportError as e:
            raise LLMSchemaError(f"LLM transport failed: {e}") from e
        except _ShapeError as e:
            last_err = f"response shape invalid: {e}"
            logger.warning("LLM shape error (attempt %d): %s", attempt, e)
            continue

        err = _validate(result)
        if err is None:
            return result

        last_err = err
        logger.warning("LLM schema validation failed (attempt %d): %s", attempt, err)

    raise LLMSchemaError(f"LLM did not return a valid evaluation: {last_err}")
