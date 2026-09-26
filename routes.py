from flask import Blueprint, jsonify, request

from db import rfq_exists
from services import (
    EvaluationFailed,
    evaluate_vendor,
    list_evaluations,
    list_rfqs,
)

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/rfqs")
def get_rfqs():
    return jsonify(list_rfqs())


@bp.post("/evaluate")
def post_evaluate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    rfq_id = data.get("rfq_id")
    vendor_text = data.get("vendor_text")

    if not isinstance(rfq_id, str) or not rfq_id.strip():
        return jsonify({"error": "rfq_id is required"}), 400
    if not isinstance(vendor_text, str) or not vendor_text.strip():
        return jsonify({"error": "vendor_text is required"}), 400

    rfq_id = rfq_id.strip()
    vendor_text = vendor_text.strip()

    if not rfq_exists(rfq_id):
        return jsonify({"error": f"unknown rfq_id: {rfq_id}"}), 400

    try:
        result = evaluate_vendor(rfq_id, vendor_text)
    except EvaluationFailed as e:
        return jsonify({"error": "evaluation failed", "detail": str(e)}), 502

    return jsonify(result)


@bp.get("/evaluations")
def get_evaluations():
    return jsonify(list_evaluations())
