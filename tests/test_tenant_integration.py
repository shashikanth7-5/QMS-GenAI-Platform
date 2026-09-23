# tests/test_tenant_integration.py
# Version@3 Sprint D: per-tenant API keys, webhook replay window,
# idempotency-key support.

import hashlib
import hmac
import time

import pytest


def _client(admin_client):
    return admin_client  # already logged-in fixture


def test_tenant_create_and_resolve():
    from services import tenant_service

    tenant, api_key = tenant_service.create_tenant(
        "acme-test",
        display_name="Acme Test",
        origin_allowlist=["https://acme.my.salesforce.com"],
        webhook_secret="whsec-test",
    )
    assert tenant["tenantId"] == "acme-test"
    assert api_key  # raw key returned once

    resolved = tenant_service.resolve_tenant("acme-test", api_key)
    assert resolved is not None
    assert resolved["tenantId"] == "acme-test"

    # Wrong key -> None.
    assert tenant_service.resolve_tenant("acme-test", "wrong-key") is None

    # Revoke.
    assert tenant_service.revoke_tenant("acme-test") is True
    assert tenant_service.resolve_tenant("acme-test", api_key) is None


def test_api_v1_rejects_unknown_tenant(client):
    r = client.get(
        "/api/v1/records",
        headers={"X-API-Key": "nope", "X-Tenant-Id": "does-not-exist"},
    )
    assert r.status_code in (401, 503)


def test_api_v1_accepts_valid_tenant(client):
    from services import tenant_service
    tenant, key = tenant_service.create_tenant("api-tenant-1")
    r = client.get(
        "/api/v1/records",
        headers={"X-API-Key": key, "X-Tenant-Id": "api-tenant-1"},
    )
    # Either 200 with records, or the legacy fallback path may kick in.
    assert r.status_code == 200


def test_idempotency_replay_returns_cached(client):
    """POSTing the same body with the same Idempotency-Key returns the cached response."""
    from services import tenant_service
    _, key = tenant_service.create_tenant("api-tenant-idem")
    headers = {
        "X-API-Key": key,
        "X-Tenant-Id": "api-tenant-idem",
        "Idempotency-Key": "test-idem-001",
        "Content-Type": "application/json",
    }
    body = {
        "record": {
            "id": "IDEM-REC-1", "type": "complaint", "sector": "Medical Device",
            "priority": "High", "title": "Idem test", "description": "Test body",
            "site": "Site A",
        },
    }
    r1 = client.post("/api/v1/capa/generate", json=body, headers=headers)
    assert r1.status_code in (200, 201)
    r2 = client.post("/api/v1/capa/generate", json=body, headers=headers)
    # Cached — matching key + body returns the cached response.
    assert r2.status_code in (200, 201)
    assert r2.get_json() == r1.get_json()


def test_idempotency_conflict_on_different_body(client):
    from services import tenant_service
    _, key = tenant_service.create_tenant("api-tenant-idem2")
    headers = {
        "X-API-Key": key,
        "X-Tenant-Id": "api-tenant-idem2",
        "Idempotency-Key": "test-idem-conflict",
        "Content-Type": "application/json",
    }
    r1 = client.post("/api/v1/capa/generate",
                     json={"record": {"id": "A", "type": "complaint", "sector": "Medical Device",
                                      "priority": "High", "title": "A", "description": "A",
                                      "site": "X"}},
                     headers=headers)
    assert r1.status_code in (200, 201)
    r2 = client.post("/api/v1/capa/generate",
                     json={"record": {"id": "B", "type": "deviation", "sector": "BioPharma",
                                      "priority": "Low", "title": "B", "description": "B",
                                      "site": "Y"}},
                     headers=headers)
    assert r2.status_code == 409
    body = r2.get_json() or {}
    assert body.get("code") == "idempotency_conflict"


def test_api_v1_capa_save_upserts_external_source_record(client):
    from data.records import get_record_by_id
    from services import tenant_service

    _, key = tenant_service.create_tenant("api-tenant-capa-save")
    headers = {
        "X-API-Key": key,
        "X-Tenant-Id": "api-tenant-capa-save",
        "Content-Type": "application/json",
    }
    payload = {
        "sourceRecordId": "500g800002TESTAAA",
        "sourceRecordType": "complaint",
        "sourceRecordTitle": "Salesforce complaint source",
        "sector": "BioPharma",
        "priority": "High",
        "site": "SF Site",
        "rootCause": "Documented equipment PM gap.",
        "immediateAction": "Quarantine affected stock.",
        "correctiveAction": "Complete PM and QA review.",
        "preventiveAction": "Automate PM overdue alert.",
        "capaOwner": "Quality Assurance Manager",
        "effectivenessCheck": "No recurrence for three lots.",
        "riskRating": "High",
        "estimatedClosureDays": 30,
        "regulatoryRef": ["21 CFR 820.100"],
        "createdByUsername": "salesforce.user@example.com",
    }

    response = client.post("/api/v1/capa/save", json=payload, headers=headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["sourceRecordId"] == payload["sourceRecordId"]
    assert get_record_by_id(payload["sourceRecordId"]) is not None


def test_webhook_replay_protection(client):
    """SF webhook rejects: no timestamp, stale timestamp, replayed nonce."""
    from services import tenant_service
    _, _key = tenant_service.create_tenant(
        "wh-test", webhook_secret="whsec-wh-test",
    )
    secret = "whsec-wh-test"
    body = b'{"event":"case_created","record":{"id":"WHR-1","type":"complaint",' \
           b'"sector":"Medical Device","priority":"High","title":"t",' \
           b'"description":"d","site":"x","regulatoryRef":["21 CFR 820"]}}'

    def sig(ts, nonce, body_bytes):
        payload = f"{ts}.{nonce}.".encode() + body_bytes
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    # 1. Missing headers -> 401
    r = client.post("/api/v1/webhooks/salesforce", data=body,
                    headers={"X-Tenant-Id": "wh-test", "Content-Type": "application/json"})
    assert r.status_code == 401

    # 2. Fresh + valid -> 200
    ts = str(int(time.time()))
    nonce = "nonce-fresh-1"
    r = client.post("/api/v1/webhooks/salesforce", data=body,
                    headers={
                        "X-Tenant-Id": "wh-test",
                        "X-Salesforce-Timestamp": ts,
                        "X-Salesforce-Nonce": nonce,
                        "X-Salesforce-Signature": sig(ts, nonce, body),
                        "Content-Type": "application/json",
                    })
    assert r.status_code == 200

    # 3. Same nonce replayed -> 401
    r = client.post("/api/v1/webhooks/salesforce", data=body,
                    headers={
                        "X-Tenant-Id": "wh-test",
                        "X-Salesforce-Timestamp": ts,
                        "X-Salesforce-Nonce": nonce,
                        "X-Salesforce-Signature": sig(ts, nonce, body),
                        "Content-Type": "application/json",
                    })
    assert r.status_code == 401

    # 4. Stale timestamp -> 401
    stale = str(int(time.time()) - 3600)
    r = client.post("/api/v1/webhooks/salesforce", data=body,
                    headers={
                        "X-Tenant-Id": "wh-test",
                        "X-Salesforce-Timestamp": stale,
                        "X-Salesforce-Nonce": "nonce-stale-1",
                        "X-Salesforce-Signature": sig(stale, "nonce-stale-1", body),
                        "Content-Type": "application/json",
                    })
    assert r.status_code == 401
