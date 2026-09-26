from db import (
    fetch_rfqs,
    fetch_evaluations,
    insert_evaluation,
    rfq_exists,
)


def list_rfqs():
    return fetch_rfqs()


def list_evaluations():
    return fetch_evaluations()


def evaluate_vendor(rfq_id, vendor_text):
    if not rfq_exists(rfq_id):
        raise ValueError(f"unknown rfq_id: {rfq_id}")

    score = 75
    reasons = [
        "Vendor states relevant certification (stub)",
        "Stated capacity appears aligned with RFQ quantity (stub)",
        "Delivery lead time fits the requested window (stub)",
    ]
    gaps = [
        "No evidence of preferred capability (stub)",
        "Traceability documentation not specified (stub)",
    ]

    eval_id = insert_evaluation(rfq_id, vendor_text, score, reasons, gaps)
    return {
        "id": eval_id,
        "rfq_id": rfq_id,
        "score": score,
        "reasons": reasons,
        "gaps": gaps,
    }
