from services.ai_service import _build_capa_prompt, _build_rca_prompt


def test_rca_prompt_includes_redacted_attachment_evidence():
    record = {
        "id": "500TEST",
        "type": "complaint",
        "title": "Infusion pump alarm failure",
        "description": "Device stopped during infusion.",
        "priority": "High",
        "attachments": [
            {
                "title": "investigation-notes",
                "fileType": "TEXT",
                "sizeBytes": 120,
                "textSnippet": "patient name: Jane Smith; gender: female; pump PM overdue by 42 days.",
            }
        ],
    }

    prompt = _build_rca_prompt(record, "fishbone")

    assert "ATTACHMENT EVIDENCE" in prompt
    assert "pump PM overdue by 42 days" in prompt
    assert "Jane Smith" not in prompt
    assert "female" not in prompt.lower()
    assert "[sensitive-info-redacted]" in prompt


def test_capa_prompt_uses_attachment_evidence():
    record = {
        "id": "500TEST",
        "type": "complaint",
        "sector": "Medical Device",
        "priority": "High",
        "title": "Infusion pump alarm failure",
        "description": "Device stopped during infusion.",
        "regulatoryRef": ["21 CFR 820.100"],
        "rootCause": "PM schedule gap allowed alarm sensor drift.",
        "attachments": [
            {
                "title": "service-log",
                "fileType": "TEXT",
                "sizeBytes": 140,
                "textSnippet": "contractor name: Arun Kumar; alarm calibration missed during PM.",
            }
        ],
    }

    prompt = _build_capa_prompt(record)

    assert "ATTACHMENT EVIDENCE" in prompt
    assert "alarm calibration missed during PM" in prompt
    assert "Arun Kumar" not in prompt
    assert "USER-SELECTED RCA CONTEXT" in prompt
