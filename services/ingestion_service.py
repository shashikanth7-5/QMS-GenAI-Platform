# services/ingestion_service.py
# Sprint 2: adds QMS relevance scoring.
# Unrelated files return {"_insufficient": True, "reason": "..."}
# instead of creating garbage records.

import base64
import csv
import io
import json
import os
import re
from datetime import datetime

from services.logging_config import get_logger

log = get_logger(__name__)

_SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() == "true"

ALLOWED_EXTENSIONS = {
    "pdf","xlsx","xls","csv",
    "png","jpg","jpeg","bmp","tiff","tif",
    "docx","doc","txt",
}
_IMAGE_EXTS = {"png","jpg","jpeg","bmp","tiff","tif"}
_MIME_MAP   = {
    "png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
    "bmp":"image/bmp","tiff":"image/tiff","tif":"image/tiff",
}

# ── QMS relevance keywords ─────────────────────────────────
# A file must contain a minimum density of these terms to be
# considered a QMS document. Prevents uploading tax returns,
# photos of cats, etc. and getting fabricated records.
_QMS_KEYWORDS = [
    "complaint","deviation","capa","corrective","preventive","non-conformance",
    "nonconformance","audit","change control","batch","lot","sop","gmp","gdp",
    "iso","cfr","fda","ema","cdsco","mdr","ich","usp","oos","ooc","cqa","ccp",
    "quality","regulatory","investigation","root cause","rca","manufacturing",
    "calibration","validation","sterilisation","sterilization","bioburden",
    "particulate","deviation","excursion","out-of-spec","recall","fsca",
    "adverse event","patient","product","site","owner","priority",
]
_MIN_KEYWORD_HITS = 3   # at least 3 distinct QMS keywords must appear


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS


def _check_qms_relevance(text: str) -> tuple[bool, str]:
    """
    Returns (is_relevant, reason).
    Scans extracted text for QMS keyword density.
    """
    if not text or not isinstance(text, str):
        return False, "Could not extract readable text from the document."
    lower = text.lower()
    hits  = [kw for kw in _QMS_KEYWORDS if kw in lower]
    if len(hits) < _MIN_KEYWORD_HITS:
        return False, (
            f"This document does not appear to be a QMS record "
            f"(only {len(hits)} of {_MIN_KEYWORD_HITS} required quality keywords found). "
            f"Please upload a complaint report, deviation form, change control document, "
            f"audit finding, or similar quality management record."
        )
    return True, ""


# ── Text extraction ────────────────────────────────────────
def extract_text(file_bytes: bytes, filename: str):
    ext = filename.rsplit(".",1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber not installed.")
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: parts.append(t)
        return "\n".join(parts) or "(No text found in PDF)"

    if ext in ("xlsx","xls"):
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl not installed.")
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        rows = []
        for sheet in wb.worksheets:
            rows.append(f"[Sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                clean = [str(c) if c is not None else "" for c in row]
                if any(c.strip() for c in clean):
                    rows.append("\t".join(clean))
        return "\n".join(rows)

    if ext == "csv":
        text   = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        return "\n".join("\t".join(row) for row in reader)

    if ext in _IMAGE_EXTS:
        b64 = base64.standard_b64encode(file_bytes).decode()
        return {"type":"image","b64":b64,"mime":_MIME_MAP.get(ext,"image/jpeg")}

    if ext in ("docx","doc"):
        try:
            import docx as _docx
        except ImportError:
            raise RuntimeError("python-docx not installed.")
        doc = _docx.Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    raise ValueError(f"Unsupported file format: .{ext}")


# ── AI extraction prompt ───────────────────────────────────
_PROMPT = """You are a QMS data extraction agent.
Extract ONE quality record from the document below.

IMPORTANT: If this document is NOT a quality management record (complaint, deviation,
change control, non-conformance, audit finding, or similar QMS document), respond ONLY with:
{"_insufficient": true, "reason": "Brief explanation of why this is not a QMS record and what type of document is needed"}

Otherwise return ONLY a valid JSON object — no markdown, no explanation:
{
  "id":            "Auto-generate: UPL-YYYY-NNNN",
  "type":          "complaint | deviation | cc | nc | audit",
  "sector":        "Medical Device | BioPharma | General",
  "title":         "Short issue title (max 80 chars)",
  "description":   "2-4 sentence description",
  "priority":      "Critical | High | Medium | Low",
  "site":          "Site/location or Unknown",
  "owner":         "Responsible person or Unassigned",
  "detectedDate":  "YYYY-MM-DD or today",
  "productFamily": "Product or equipment or empty string",
  "batchLot":      "Batch/lot number or empty string",
  "regulatoryRef": ["list of refs like 21 CFR, ISO, ICH or empty list"]
}

Document:
---
{content}
---"""


def ai_extract_record(extracted, filename: str) -> dict:
    from config import MOCK_MODE, AI_PROVIDER

    # ── Pre-flight relevance check for text documents ──────
    if isinstance(extracted, str):
        relevant, reason = _check_qms_relevance(extracted)
        if not relevant:
            return {"_insufficient": True, "reason": reason}

    # ── Pre-flight relevance check for image uploads ──────
    # Without this, an unrelated image (cat photo, screenshot) triggers a
    # multi-modal LLM call and gets stored as a QMS record with hallucinated
    # fields. We only allow images whose filename hints at QMS content.
    is_image = isinstance(extracted, dict) and extracted.get("type") == "image"
    if is_image:
        stem = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
        _IMAGE_HINTS = (
            "capa", "deviation", "complaint", "audit", "batch", "lot",
            "quality", "nc", "non-conformance", "nonconformance",
            "sop", "form", "report", "investigation", "change control",
            "recall", "adverse", "root cause",
        )
        if not any(h in stem for h in _IMAGE_HINTS):
            return {
                "_insufficient": True,
                "reason": (
                    "Image filename does not indicate QMS content. Rename with a "
                    "QMS keyword (CAPA, deviation, complaint, audit, batch, etc.) "
                    "or upload the source document instead of a screenshot."
                ),
            }

    from services.ai_service import _provider_configs
    configs = _provider_configs()
    if MOCK_MODE or AI_PROVIDER == "mock" or not configs:
        return _mock_extract(filename)

    try:
        import httpx
        from services.guardrails import sanitize_prompt_text
        cfg = configs[0]
        provider = cfg["provider"]
        api_key = cfg["api_key"]
        model = cfg["model"]
        base_url = cfg.get("base_url", "")
        if provider == "anthropic":
            user_content = (
                [
                    {"type":"image","source":{"type":"base64","media_type":extracted["mime"],"data":extracted["b64"]}},
                    {"type":"text","text":_PROMPT.replace("{content}","[see image above]")},
                ]
                if is_image
                else _PROMPT.replace("{content}", sanitize_prompt_text(extracted, max_len=6000))
            )
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key":api_key,"anthropic-version":"2023-06-01","content-type":"application/json"},
                json={"model":model,"max_tokens":900,"messages":[{"role":"user","content":user_content}]},
                timeout=40,
                verify=_SSL_VERIFY,
            )
            raw = resp.json()["content"][0]["text"]

        elif provider in ("openai","azure","groq"):
            base = base_url or (
                "https://api.groq.com/openai/v1"
                if provider == "groq"
                else "https://api.openai.com/v1"
            )
            user_content = (
                [
                    {"type":"text","text":_PROMPT.replace("{content}","[see image]")},
                    {"type":"image_url","image_url":{"url":f"data:{extracted['mime']};base64,{extracted['b64']}"}},
                ]
                if is_image
                else _PROMPT.replace("{content}", sanitize_prompt_text(extracted, max_len=6000))
            )
            resp = httpx.post(f"{base}/chat/completions",
                headers={"Authorization":f"Bearer {api_key}"},
                json={"model":model,"messages":[{"role":"user","content":user_content}]},
                timeout=40,
                verify=_SSL_VERIFY,
            )


            raw = resp.json()["choices"][0]["message"]["content"]
        else:
            return _mock_extract(filename)

        raw    = re.sub(r"```json|```","",raw).strip()
        record = json.loads(raw)

        # Check if AI itself flagged insufficiency
        if record.get("_insufficient"):
            return record

        record.update({"status":"Draft Generated","age":0,"_source":"uploaded"})
        return record

    except Exception:
        log.warning("ingestion.ai_extraction_failed", exc_info=True)
        return _mock_extract(filename)


def _mock_extract(filename: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    uid   = datetime.now().strftime("%m%d%H%M")
    name  = os.path.splitext(filename)[0].replace("_"," ").replace("-"," ").title()
    return {
        "id":            f"UPL-{datetime.now().year}-{uid}",
        "type":          "complaint",
        "sector":        "Medical Device",
        "title":         name[:80] or "Uploaded Quality Record",
        "description":   f"Record extracted from: {filename}. Review and update all fields.",
        "priority":      "High",
        "status":        "Draft Generated",
        "site":          "Unknown",
        "owner":         "Unassigned",
        "detectedDate":  today,
        "productFamily": "",
        "batchLot":      "",
        "regulatoryRef": [],
        "age":           0,
        "_source":       "uploaded",
    }


def process_upload(file_bytes: bytes, filename: str) -> dict:
    if not allowed_file(filename):
        raise ValueError(f"Unsupported type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    extracted = extract_text(file_bytes, filename)
    return ai_extract_record(extracted, filename)
