# routes/api_v1.py
# ══════════════════════════════════════════════════════════════
# QMS GenAI — REST API v1
# X-API-Key authenticated, host-exact CORS, CSRF-exempt (bearer auth).
# ══════════════════════════════════════════════════════════════

import hashlib
import hmac
import os
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request

from auth.users import get_user_by_username
from config import (API_V1_ALLOW_ANONYMOUS, API_V1_KEY, CORS_ORIGINS,
                    RATE_LIMIT_API_V1, SF_WEBHOOK_SECRET)
from data.records import (get_all_capas, get_all_records, get_capa_by_id,
                          get_record_by_id, save_capa, update_capa_status,
                          upsert_external_record)
from services.ai_service import generate_capa
from services.agents.langgraph_workflow import run_capa_workflow
from services.logging_config import get_logger
from services.security import capa_content_hash
from services.workflow_config import (is_agent_eligible, normalize_record_type,
                                      workflow_snapshot)

log = get_logger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ── CORS helper (host-exact + optional wildcard subdomain suffix) ─
def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    for pattern in CORS_ORIGINS:
        pattern = pattern.strip()
        if not pattern:
            continue
        try:
            p = urlparse(pattern)
        except ValueError:
            continue
        if p.scheme.lower() != scheme:
            continue
        p_host = p.netloc.lower()
        if p_host.startswith("*."):
            suffix = p_host[1:]  # ".salesforce.com"
            if host == suffix.lstrip(".") or host.endswith(suffix):
                return True
        elif p_host == host:
            return True
    return False


def _add_cors(response):
    origin = request.headers.get("Origin", "")
    if _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
    return response


@api_v1_bp.after_request
def after_request(response):
    """CORS + idempotency response persistence."""
    from flask import g
    from services import tenant_service
    key = getattr(g, "qms_idempotency_key", None)
    tenant = getattr(g, "qms_tenant", None)
    # Only store successful state-changing responses (2xx). Skip 5xx so a
    # retry can go through, and skip <=1MB bodies to avoid caching giant payloads.
    if (key and tenant and request.method in ("POST", "PUT", "PATCH", "DELETE")
            and 200 <= response.status_code < 300):
        try:
            body_json = response.get_json(silent=True) or {}
            tenant_service.store_idempotent_response(
                tenant_id=tenant["tenantId"], key=key,
                method=request.method, path=request.path,
                request_body=request.get_data(cache=True),
                status_code=response.status_code, response_json=body_json,
            )
        except Exception:
            log.warning("api_v1.idempotency_store_failed", exc_info=True)
        g.qms_idempotency_key = None  # prevent double-store
    return _add_cors(response)


@api_v1_bp.route("/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    return _add_cors(jsonify({"status": "ok"}))


# ── Authentication decorator (per-tenant with legacy single-key fallback) ──
def require_api_key(fn):
    """Resolve caller against qms_api_tenants. Legacy single-key mode kicks in
    only when the tenants table is empty AND API_V1_KEY is set."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from services import run_context, tenant_service
        from flask import g

        api_key = (request.headers.get("X-API-Key") or request.args.get("api_key") or "").strip()
        tenant_id = (request.headers.get("X-Tenant-Id") or "").strip() or "_legacy"

        # Anonymous shortcut: only when no key is presented AND the server
        # is configured for anonymous. If a caller provides a key we always
        # validate it (never silently accept), so tests can assert 401 on
        # a bad key even in dev/test mode.
        if not api_key:
            if not API_V1_KEY and API_V1_ALLOW_ANONYMOUS:
                return fn(*args, **kwargs)
            return jsonify({
                "error": "unauthorized",
                "message": "X-API-Key header is required",
                "code": "missing_key",
            }), 401

        tenant = tenant_service.resolve_tenant(tenant_id, api_key)
        if not tenant:
            log.warning("api_v1.auth.rejected",
                        extra={"path": request.path, "tenant_id": tenant_id,
                               "ip": request.remote_addr})
            return jsonify({
                "error": "unauthorized",
                "message": "Valid X-API-Key + X-Tenant-Id required",
                "code": "invalid_credentials",
            }), 401

        # Bind tenant + user context so logs and audit rows carry it.
        run_context.set_tenant_id(tenant["tenantId"])
        g.qms_tenant = tenant
        # Idempotency-Key check for state-changing calls.
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if idempotency_key and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            cached, conflict = tenant_service.check_and_record_idempotency(
                tenant_id=tenant["tenantId"], key=idempotency_key,
                method=request.method, path=request.path,
                request_body=request.get_data(cache=True),
            )
            if conflict:
                return jsonify(conflict), 409
            if cached:
                return jsonify(cached.get("response_json") or {}), int(cached.get("status_code") or 200)
            g.qms_idempotency_key = idempotency_key
        return fn(*args, **kwargs)
    return wrapper


def _maybe_store_idempotency(response_body: dict, status_code: int) -> None:
    """Called from route handlers after a successful state-changing call."""
    from flask import g
    from services import tenant_service
    key = getattr(g, "qms_idempotency_key", None)
    tenant = getattr(g, "qms_tenant", None)
    if not key or not tenant:
        return
    tenant_service.store_idempotent_response(
        tenant_id=tenant["tenantId"], key=key,
        method=request.method, path=request.path,
        request_body=request.get_data(cache=True),
        status_code=status_code,
        response_json=response_body or {},
    )


def _apply_rate_limits():
    limiter = current_app.extensions.get("qms_limiter") if current_app else None
    if not limiter:
        return
    try:
        limiter.limit(RATE_LIMIT_API_V1)(api_v1_bp)
    except Exception:
        log.exception("api_v1.rate_limit_attach_failed")


@api_v1_bp.record_once
def _on_registered(setup_state):
    with setup_state.app.app_context():
        _apply_rate_limits()


# ── Standard response wrapper ─────────────────────────────────
def _ok(data, status=200):
    return jsonify({
        "status":    "success",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data":      data,
    }), status


def _err(message, status=400, code=None):
    return jsonify({
        "status":  "error",
        "error":   code or "bad_request",
        "message": message,
    }), status


def _external_user(body: dict) -> dict:
    user = body.get("user") or body.get("currentUser") or {}
    username = (
        user.get("username")
        or user.get("userName")
        or user.get("email")
        or body.get("triggeredBy")
        or "external-user"
    )
    return {
        "username": username,
        "fullName": user.get("fullName") or user.get("name") or username,
        "email": user.get("email", ""),
        "role": user.get("role") or user.get("profile") or "external",
    }


def _normalize_external_record(body: dict) -> dict:
    source = body.get("externalSystem") or body.get("sourceSystem") or "external_qms"
    record = dict(body.get("record") or body.get("qualityEvent") or {})
    if not record:
        raise ValueError("record or qualityEvent payload is required")
    record_id = (
        record.get("id")
        or record.get("recordId")
        or record.get("externalId")
        or record.get("caseId")
    )
    if not record_id:
        raise ValueError("External record requires id, recordId, externalId, or caseId")
    user = _external_user(body)
    record["id"] = record_id
    record["type"] = normalize_record_type(record.get("type") or record.get("category") or record.get("eventType"))
    record["status"] = record.get("status") or record.get("workflowState") or "Draft Generated"
    record["title"] = record.get("title") or record.get("subject") or f"Quality Event {record_id}"
    record["description"] = record.get("description") or record.get("details") or record.get("summary") or ""
    record["priority"] = record.get("priority") or record.get("riskRating") or "Medium"
    record["sector"] = record.get("sector") or record.get("businessUnit") or "Medical Device"
    record["owner"] = record.get("owner") or user["username"]
    record["createdBy"] = user["username"]
    record["_source"] = source
    record["external"] = {
        "system": source,
        "objectType": body.get("objectType") or record.get("objectType") or "QualityEvent",
        "callbackUrl": body.get("callbackUrl", ""),
    }
    return record


# ══════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/health", methods=["GET"])
def health():
    from services.ai_service import llm_status
    return _ok({
        "service":   "QMS GenAI",
        "version":   "1.0",
        "status":    "healthy",
        "records":   len(get_all_records()),
        "capas":     len(get_all_capas()),
        "mock_mode": os.getenv("MOCK_MODE", "true"),
        "llm":        llm_status(),
    })


@api_v1_bp.route("/workflow-config", methods=["GET"])
@require_api_key
def api_workflow_config():
    return _ok(workflow_snapshot())


@api_v1_bp.route("/integrations/quality-event/capa", methods=["POST"])
@require_api_key
def api_external_quality_event_capa():
    """Entry point for TrackWise/Salesforce 'Create CAPA with AI' actions."""
    body = request.get_json(silent=True) or {}
    options = body.get("options") or {}
    user = _external_user(body)
    try:
        normalized = _normalize_external_record(body)
    except ValueError as exc:
        return _err(str(exc), 400, "invalid_external_record")

    eligible, reason = is_agent_eligible(normalized)
    imported = upsert_external_record(normalized)
    if not eligible and not options.get("force", False):
        return _ok({
            "integrationStatus": "skipped",
            "reason": reason,
            "record": imported,
            "workflow": workflow_snapshot(),
            "ui": {
                "showMessage": reason,
                "allowManualFallback": True,
                "radioButtonAction": "disabled_by_workflow_state",
            },
        }, 202)

    save_draft = options.get("saveDraft", True)
    result = run_capa_workflow(
        imported["id"],
        triggered_by=user["username"],
        save_draft=save_draft,
        decision_answers=body.get("answers") or body.get("decisionAnswers"),
    )
    saved = result.get("savedCapa") or {}
    capa_id = saved.get("capaId") or (result.get("draft") or {}).get("capaId")
    review_state = saved.get("status") or ("Draft Generated" if result.get("draft") else "Not Triggered")
    return _ok({
        "integrationStatus": "completed" if result.get("status") == "ok" else "error",
        "externalSystem": normalized.get("_source"),
        "triggeredBy": user,
        "record": imported,
        "agentRun": {
            "id": result.get("agentRunId"),
            "status": result.get("status"),
            "capaTriggered": result.get("capaTriggered"),
            "turnsUsed": result.get("turnsUsed"),
            # steps[] intentionally trimmed to `agent` + `event` + `status`
            # so we do not leak internal prompts, LLM reasoning, or provider
            # metadata to TrackWise / Salesforce integrations.
            "steps": [
                {
                    "agent": step.get("agent"),
                    "event": step.get("event") or step.get("action"),
                    "status": step.get("status"),
                }
                for step in (result.get("steps") or [])
                if isinstance(step, dict)
            ],
            "error": result.get("error"),
        },
        "capa": {
            "id": capa_id,
            "draft": result.get("draft"),
            "saved": saved or None,
            "reviewState": review_state,
            "requiresHumanApproval": result.get("requiresHumanApproval", True),
            "eSignatureRequiredFor": workflow_snapshot().get("esign", {}).get("required_for", ["Approved", "Rejected"]),
        },
        "ui": {
            "radioButtonAction": "create_capa_with_ai",
            "showSubmitForReview": bool(saved),
            "showApproveReject": bool(saved),
            "openDraftUrl": f"/capa/create?id={imported['id']}&capaId={capa_id}" if capa_id else "",
            "manualFallbackAvailable": True,
        },
        "notifications": {
            "creatorEmail": user.get("email", ""),
            "approvalEmailAvailable": bool(user.get("email")),
        },
        "workflow": workflow_snapshot(),
    }, 201 if saved else 200)


# ══════════════════════════════════════════════════════════════
# RECORDS
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/records", methods=["GET"])
@require_api_key
def list_records():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = max(1, min(100, int(request.args.get("per_page", 25))))
    except (TypeError, ValueError):
        return _err("page and per_page must be positive integers", 400, "invalid_pagination")
    rtype    = request.args.get("type")
    sector   = request.args.get("sector")
    priority = request.args.get("priority")
    status   = request.args.get("status")
    q        = (request.args.get("q") or "").lower().strip()

    recs = get_all_records()
    if rtype:    recs = [r for r in recs if r.get("type")     == rtype]
    if sector:   recs = [r for r in recs if r.get("sector")   == sector]
    if priority: recs = [r for r in recs if r.get("priority") == priority]
    if status:   recs = [r for r in recs if r.get("status")   == status]
    if q:
        recs = [r for r in recs if q in r.get("id", "").lower()
                or q in r.get("title", "").lower()
                or q in r.get("description", "").lower()]

    total = len(recs)
    start = (page - 1) * per_page
    return _ok({
        "records":  recs[start:start + per_page],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
        "has_next": start + per_page < total,
        "has_prev": page > 1,
    })


@api_v1_bp.route("/records/<record_id>", methods=["GET"])
@require_api_key
def get_record(record_id):
    rec = get_record_by_id(record_id)
    if not rec:
        return _err(f"Record {record_id} not found", 404, "not_found")
    return _ok(rec)


# ══════════════════════════════════════════════════════════════
# CAPA
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/capa/generate", methods=["POST"])
@require_api_key
def api_generate_capa():
    body = request.get_json(silent=True) or {}
    record = body.get("record")
    if not record:
        rid = body.get("record_id") or body.get("recordId")
        if not rid:
            return _err("Provide record_id or record object", 400)
        record = get_record_by_id(rid)
        if not record:
            return _err(f"Record {rid} not found", 404, "not_found")
    try:
        capa = generate_capa(record)
        return _ok({
            "capa":          capa,
            "source_record": record.get("id"),
            "generated_at":  datetime.utcnow().isoformat() + "Z",
        }, 201)
    except Exception as exc:
        log.exception("api_v1.capa.generate_failed")
        return _err(f"CAPA generation failed: {exc}", 500, "generation_error")


@api_v1_bp.route("/capa/save", methods=["POST"])
@require_api_key
def api_save_capa():
    import uuid
    body = request.get_json(silent=True) or {}
    if not body.get("sourceRecordId"):
        return _err("sourceRecordId is required", 400)

    capa_id = f"CAPA-{datetime.now().year}-{uuid.uuid4().hex[:12].upper()}"
    capa_record = {
        "capaId":             capa_id,
        "sourceRecordId":     body.get("sourceRecordId"),
        "sourceRecordType":   body.get("sourceRecordType", ""),
        "sourceRecordTitle":  body.get("sourceRecordTitle", ""),
        "sector":             body.get("sector", ""),
        "priority":           body.get("priority", "Medium"),
        "site":               body.get("site", ""),
        "status":             "Under Review",
        "rootCause":          body.get("rootCause", ""),
        "immediateAction":    body.get("immediateAction", ""),
        "correctiveAction":   body.get("correctiveAction", ""),
        "preventiveAction":   body.get("preventiveAction", ""),
        "capaOwner":          body.get("capaOwner", ""),
        "effectivenessCheck": body.get("effectivenessCheck", ""),
        "riskRating":         body.get("riskRating", "Medium"),
        "regulatoryRef":      body.get("regulatoryRef", []),
        "estimatedClosureDays": body.get("estimatedClosureDays", 30),
        "notes":              body.get("notes", ""),
        "createdBy":          body.get("createdBy", "api"),
        "createdByUsername":  body.get("createdByUsername", "api"),
        "createdByRole":      body.get("createdByRole", "api"),
        "createdAt":          datetime.utcnow().isoformat(),
        "updatedAt":          datetime.utcnow().isoformat(),
        "_source":            "api_v1",
    }
    save_capa(capa_record)
    return _ok({"capaId": capa_id, "status": "Under Review"}, 201)


@api_v1_bp.route("/capas", methods=["GET"])
@require_api_key
def list_capas():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = max(1, min(100, int(request.args.get("per_page", 25))))
    except (TypeError, ValueError):
        return _err("page and per_page must be positive integers", 400, "invalid_pagination")
    status   = request.args.get("status")
    capas    = get_all_capas()
    if status:
        capas = [c for c in capas if c.get("status") == status]
    total    = len(capas)
    start    = (page - 1) * per_page
    return _ok({
        "capas":    capas[start:start + per_page],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
    })


@api_v1_bp.route("/capas/<capa_id>", methods=["GET"])
@require_api_key
def get_capa(capa_id):
    capa = get_capa_by_id(capa_id)
    if not capa:
        return _err(f"CAPA {capa_id} not found", 404, "not_found")
    return _ok(capa)


@api_v1_bp.route("/capas/<capa_id>/status", methods=["PATCH"])
@require_api_key
def update_status(capa_id):
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    valid = ["Under Review", "Pending Correction", "Approved", "Rejected", "Closed"]
    if status not in valid:
        return _err(f"status must be one of: {', '.join(valid)}", 400)

    existing = get_capa_by_id(capa_id)
    if not existing:
        return _err(f"CAPA {capa_id} not found", 404, "not_found")

    metadata = dict(existing.get("capaMetadata") or {})
    reviewer_username = ""
    comment = body.get("comment", "")
    workflow_status = "Pending Correction" if status == "Rejected" else status

    if status in ("Approved", "Rejected"):
        esign = body.get("eSignature") or {}
        reviewer_username = esign.get("signedBy") or esign.get("username") or ""
        password = esign.get("password") or ""
        meaning = esign.get("meaning") or ""

        if not reviewer_username or not password or not meaning:
            return _err(
                "eSignature.signedBy, eSignature.password and eSignature.meaning are required "
                "for approval/rejection (21 CFR §11.200).",
                400,
                "esign_required",
            )

        reviewer = get_user_by_username(reviewer_username)
        if not reviewer or not reviewer.check_password(password):
            log.warning(
                "api_v1.esign.rejected",
                extra={"capa_id": capa_id, "signer": reviewer_username, "ip": request.remote_addr},
            )
            return _err(
                "Electronic signature password did not match the named reviewer.",
                403,
                "esign_invalid",
            )

        if status == "Approved" and reviewer.role != "admin":
            return _err(
                "Only an admin reviewer may approve a CAPA (21 CFR §820.20).",
                403,
                "esign_role_denied",
            )

        body_hash = capa_content_hash(existing)
        signature = {
            "signedBy": reviewer.username,
            "signedByRole": reviewer.role,
            "meaning": meaning,
            "decision": status,
            "signedAt": datetime.utcnow().isoformat() + "Z",
            "capaHash": body_hash,
            "basis": ["21 CFR Part 11 §11.200", "EU Annex 11"],
            "source": "api_v1",
        }
        metadata.setdefault("electronicSignatures", []).append(signature)
        metadata["lastReview"] = {
            "decision": status,
            "workflowStatus": workflow_status,
            "comment": comment,
            "reviewedBy": reviewer.username,
            "reviewedAt": signature["signedAt"],
            "eSignature": signature,
        }
        log.info(
            "api_v1.capa.status_changed",
            extra={
                "capa_id": capa_id,
                "status": workflow_status,
                "requested": status,
                "signer": reviewer.username,
            },
        )

    updated = update_capa_status(
        capa_id,
        workflow_status,
        rejected_by=reviewer_username,
        rejection_comment=comment,
        capa_metadata=metadata,
    )
    if not updated:
        return _err(f"CAPA {capa_id} not found", 404, "not_found")
    return _ok({"capaId": capa_id, "status": workflow_status, "requestedStatus": status})


# ══════════════════════════════════════════════════════════════
# RCA
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/rca/analyze", methods=["POST"])
@require_api_key
def api_rca():
    body = request.get_json(silent=True) or {}
    method = body.get("method", "fishbone")
    record = body.get("record")
    if not record:
        rid = body.get("record_id") or body.get("recordId")
        if not rid:
            return _err("Provide record_id or record object", 400)
        record = get_record_by_id(rid)
        if not record:
            return _err(f"Record {rid} not found", 404, "not_found")
    try:
        from services.ai_service import generate_rca
        rca = generate_rca(record, method)
        return _ok({"rca": rca, "method": method})
    except Exception as exc:
        log.exception("api_v1.rca.failed")
        return _err(str(exc), 500, "rca_error")


@api_v1_bp.route("/rca/propose", methods=["POST"])
@require_api_key
def api_rca_propose():
    body = request.get_json(silent=True) or {}
    method = body.get("method", "fishbone")
    record = body.get("record")
    if not record:
        rid = body.get("record_id") or body.get("recordId")
        if not rid:
            return _err("Provide record_id or record object", 400)
        record = get_record_by_id(rid)
        if not record:
            return _err(f"Record {rid} not found", 404, "not_found")
    try:
        from services.ai_service import propose_rca_models
        proposals = propose_rca_models(record, method)
        return _ok(proposals)
    except Exception as exc:
        log.exception("api_v1.rca_propose.failed")
        return _err(str(exc), 500, "rca_propose_error")


@api_v1_bp.route("/rca/assess", methods=["POST"])
@require_api_key
def api_rca_assess():
    body = request.get_json(silent=True) or {}
    method = body.get("method", "fishbone")
    rca_data = body.get("rca_data") or body.get("rcaData") or {}
    if not rca_data:
        return _err("Provide rca_data", 400)
    try:
        from services.rca_service import assess_fishbone, assess_five_why
        if method == "fishbone":
            return _ok(assess_fishbone(rca_data))
        return _ok(assess_five_why(rca_data))
    except Exception as exc:
        log.exception("api_v1.rca_assess.failed")
        return _err(str(exc), 500, "rca_assess_error")


# ══════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/analytics", methods=["GET"])
@require_api_key
def api_analytics():
    from collections import Counter
    from services.analytics_service import (priority_distribution,
                                            status_pipeline, type_breakdown)
    try:
        capas = get_all_capas()
        counts = Counter(c.get("status", "Unknown") for c in capas)
        return _ok({
            "priority":    priority_distribution(),
            "status":      status_pipeline(),
            "type":        type_breakdown(),
            "capa_status": {
                "labels": ["Under Review", "Approved", "Rejected", "Closed"],
                "values": [counts.get(s, 0) for s in
                           ["Under Review", "Approved", "Rejected", "Closed"]],
                "total":  len(capas),
            },
        })
    except Exception as exc:
        log.exception("api_v1.analytics.failed")
        return _err(str(exc), 500)


# ══════════════════════════════════════════════════════════════
# SALESFORCE WEBHOOK
# ══════════════════════════════════════════════════════════════
# Webhook replay window (Salesforce clock skew < 5 min is standard).
_WEBHOOK_MAX_SKEW_SECONDS = int(os.getenv("WEBHOOK_MAX_SKEW_SECONDS", "300"))


def _verify_webhook_headers(secret: str, body_bytes: bytes) -> tuple[bool, str]:
    """
    Signature scheme: sig = HMAC-SHA256(secret, f"{timestamp}.{nonce}.{body}").
    All three headers are required; every (tenant, nonce) pair must be unique
    within the replay window to prevent replay attacks.
    Returns (ok, error_message).
    """
    import time as _time
    from services import tenant_service

    timestamp = request.headers.get("X-Salesforce-Timestamp", "").strip()
    nonce = request.headers.get("X-Salesforce-Nonce", "").strip()
    sig = request.headers.get("X-Salesforce-Signature", "").strip()

    if not (timestamp and nonce and sig):
        return False, "Missing X-Salesforce-Timestamp / X-Salesforce-Nonce / X-Salesforce-Signature"
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False, "X-Salesforce-Timestamp must be a unix epoch integer"
    if abs(int(_time.time()) - ts_int) > _WEBHOOK_MAX_SKEW_SECONDS:
        return False, f"Timestamp outside {_WEBHOOK_MAX_SKEW_SECONDS}s replay window"

    payload = f"{timestamp}.{nonce}.".encode() + (body_bytes or b"")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False, "Invalid signature"

    tenant_id = (request.headers.get("X-Tenant-Id") or "_legacy").strip()
    if not tenant_service.record_webhook_nonce(tenant_id=tenant_id, nonce=nonce):
        return False, "Nonce already used (replay detected)"
    return True, ""


@api_v1_bp.route("/webhooks/salesforce", methods=["POST"])
def salesforce_webhook():
    """Salesforce → QMS quality event webhook.

    Signature scheme:
        sig = HMAC-SHA256(secret, "<timestamp>.<nonce>.<raw_body>").hexdigest()

    Required headers:
        X-Tenant-Id             per-tenant identifier
        X-Salesforce-Timestamp  unix epoch seconds (5-minute skew tolerated)
        X-Salesforce-Nonce      unique per request (replay-guarded)
        X-Salesforce-Signature  hex-encoded HMAC-SHA256
    """
    from services import run_context
    tenant_id = (request.headers.get("X-Tenant-Id") or "").strip()
    if not tenant_id:
        return _err("X-Tenant-Id header is required", 400, "missing_tenant")

    # Resolve per-tenant webhook secret. Legacy fallback uses SF_WEBHOOK_SECRET
    # if no tenant exists yet (bootstrap phase only).
    tenant_row = None
    if tenant_id not in ("_legacy", "default"):
        # Resolve secret without needing the tenant's API key — we
        # look up by tenant_id and read webhook_secret directly.
        try:
            from database import SessionLocal
            from models import ApiTenant
            with SessionLocal() as session:
                row = session.query(ApiTenant).filter(
                    ApiTenant.tenant_id == tenant_id,
                    ApiTenant.status == "active",
                ).first()
                if row:
                    tenant_row = row.to_dict()
                    tenant_row["webhookSecret"] = row.webhook_secret or ""
        except Exception:
            log.warning("sf_webhook.tenant_lookup_failed", exc_info=True)

    secret = (tenant_row or {}).get("webhookSecret") or SF_WEBHOOK_SECRET
    if not secret:
        log.error("api_v1.sf_webhook.disabled_no_secret", extra={"tenant_id": tenant_id})
        return _err("Salesforce webhook is disabled: signing secret not configured.", 503, "webhook_disabled")

    ok, err = _verify_webhook_headers(secret, request.data)
    if not ok:
        log.warning("api_v1.sf_webhook.rejected",
                    extra={"tenant_id": tenant_id, "reason": err, "ip": request.remote_addr})
        return _err(err, 401, "unauthorized")

    run_context.set_tenant_id(tenant_id)
    body = request.get_json(silent=True) or {}
    event = body.get("event", "unknown")

    if event == "case_created" and body.get("record"):
        try:
            record = body["record"]
            capa = generate_capa(record)
            return _ok({
                "action":     "capa_generated",
                "capa_draft": capa,
                "case_id":    body.get("caseId"),
                "tenant_id":  tenant_id,
            })
        except Exception as exc:
            log.exception("api_v1.sf_webhook.capa_generation_failed")
            return _err(str(exc), 500)

    return _ok({"action": "received", "event": event, "tenant_id": tenant_id})
