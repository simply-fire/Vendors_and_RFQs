from db import (
    fetch_evaluations,
    fetch_rfq,
    fetch_rfqs,
    insert_evaluation,
)
from llm import LLMSchemaError, evaluate_with_llm


class EvaluationFailed(Exception):
    """Raised when the LLM cannot produce a valid evaluation result."""


def list_rfqs():
    return fetch_rfqs()


def list_evaluations():
    return fetch_evaluations()


def evaluate_vendor(rfq_id, vendor_text):
    rfq = fetch_rfq(rfq_id)
    if rfq is None:
        raise ValueError(f"unknown rfq_id: {rfq_id}")

    try:
        result = evaluate_with_llm(rfq, vendor_text)
    except LLMSchemaError as e:
        raise EvaluationFailed(str(e)) from e

    eval_id = insert_evaluation(
        rfq_id=rfq_id,
        vendor_text=vendor_text,
        score=result["score"],
        reasons=result["reasons"],
        gaps=result["gaps"],
    )
    return {
        "id": eval_id,
        "rfq_id": rfq_id,
        "score": result["score"],
        "reasons": result["reasons"],
        "gaps": result["gaps"],
    }
