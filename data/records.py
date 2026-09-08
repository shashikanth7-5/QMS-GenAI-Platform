# data/records.py
import random
import string
from datetime import date, datetime
from typing import Dict, List, Optional

from database import SessionLocal
from models import AuditLog, CAPARecord, QualityRecord
from services.logging_config import get_logger

log = get_logger(__name__)


def _age(detected_date):
    if not detected_date:
        return 0
    try:
        d = datetime.strptime(detected_date[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 0


def _seed_if_empty():
    _SEED = [
        {"id":"QR-2024-001","type":"complaint","sector":"Medical Device","title":"Sterility Failure - Lot 2024-A","priority":"Critical","status":"Draft Generated","site":"Site A - Chennai","owner":"R. Patel","detectedDate":"2024-01-15","description":"Sterility test failure detected on finished product lot 2024-A during QC release testing. Two positive growth results observed out of 10 samples tested.","regulatoryRef":["21 CFR Part 820","ISO 13485:2016","EU MDR 2017/745"]},
        {"id":"QR-2024-002","type":"deviation","sector":"BioPharma","title":"Temperature Excursion - Cold Storage","priority":"High","status":"Draft Generated","site":"Site B - Mumbai","owner":"A. Sharma","detectedDate":"2024-02-03","description":"Cold storage unit 3B recorded temperatures between 8-12 degrees C for approximately 4 hours due to compressor malfunction.","regulatoryRef":["21 CFR Part 211","ICH Q1A","WHO TRS 961"]},
        {"id":"QR-2024-003","type":"cc","sector":"Medical Device","title":"Raw Material Supplier Change","priority":"Medium","status":"Draft Generated","site":"Site A - Chennai","owner":"S. Kumar","detectedDate":"2024-02-20","description":"Proposed change of primary raw material supplier for catheter tubing from Supplier A to Supplier B due to supply chain constraints.","regulatoryRef":["21 CFR Part 820.70","ISO 13485 Section 7.4","EU MDR Annex IX"]},
        {"id":"QR-2024-004","type":"complaint","sector":"BioPharma","title":"Particulate Matter in Injectable","priority":"Critical","status":"Draft Generated","site":"Site C - Hyderabad","owner":"M. Reddy","detectedDate":"2024-03-10","description":"Customer complaint received regarding visible particulate matter observed in injectable product vial.","regulatoryRef":["21 CFR Part 211.192","USP 788","EU GMP Annex 1"]},
        {"id":"QR-2024-005","type":"nc","sector":"Medical Device","title":"Dimensional Out-of-Spec - Implant","priority":"High","status":"Draft Generated","site":"Site A - Chennai","owner":"P. Nair","detectedDate":"2024-03-22","description":"Incoming inspection identified dimensional non-conformance on titanium implant components. 3 out of 50 samples outside specification.","regulatoryRef":["ISO 13485:2016 Section 8.3","21 CFR 820.90","ASTM F136"]},
        {"id":"QR-2024-006","type":"audit","sector":"BioPharma","title":"GMP Audit Finding - Documentation","priority":"Medium","status":"Draft Generated","site":"Site B - Mumbai","owner":"K. Singh","detectedDate":"2024-04-05","description":"Internal GMP audit identified gaps in batch record documentation practices. Incomplete entries found in 4 out of 20 batch records reviewed.","regulatoryRef":["21 CFR Part 211.68","EU GMP Chapter 4","ICH Q10"]},
        {"id":"QR-2024-007","type":"deviation","sector":"Medical Device","title":"Equipment Calibration Overdue","priority":"Medium","status":"Draft Generated","site":"Site D - Bangalore","owner":"V. Rao","detectedDate":"2024-04-18","description":"Routine equipment audit identified that 3 critical measurement devices are past their scheduled calibration dates.","regulatoryRef":["ISO 13485:2016 Section 7.6","21 CFR 820.72","OIML R 111"]},
        {"id":"QR-2024-008","type":"complaint","sector":"BioPharma","title":"Label Misprint - Dosage Information","priority":"High","status":"Draft Generated","site":"Site C - Hyderabad","owner":"D. Mehta","detectedDate":"2024-05-02","description":"Post-market surveillance identified incorrect dosage information on product labels. Affects one batch of 10,000 units.","regulatoryRef":["21 CFR Part 201","EU FMD 2011/62","ISO 15223-1"]},
        {"id":"QR-2024-009","type":"cc","sector":"BioPharma","title":"Manufacturing Process Parameter Change","priority":"High","status":"Draft Generated","site":"Site B - Mumbai","owner":"A. Sharma","detectedDate":"2024-05-15","description":"Proposed change to fermentation process parameters to improve yield.","regulatoryRef":["ICH Q8","21 CFR 314.70","EMA Process Validation Guidelines"]},
        {"id":"QR-2024-010","type":"nc","sector":"Medical Device","title":"Packaging Integrity Failure","priority":"Critical","status":"Draft Generated","site":"Site A - Chennai","owner":"R. Patel","detectedDate":"2024-06-01","description":"Seal integrity testing failed on sterile packaging for cardiac devices. Failure rate of 2.5 percent observed during routine in-process testing.","regulatoryRef":["ISO 11607","ASTM F2097","21 CFR 820.130"]},
        {"id":"QR-2024-011","type":"complaint","sector":"Medical Device","title":"Device Malfunction - Pressure Sensor","priority":"Critical","status":"Draft Generated","site":"Site A - Chennai","owner":"S. Kumar","detectedDate":"2024-06-20","description":"Three customer reports of pressure sensor malfunction in infusion pump devices. One incident resulted in incorrect drug delivery.","regulatoryRef":["21 CFR Part 803","MDR 2017/745 Article 87","ISO 14971"]},
        {"id":"QR-2024-012","type":"deviation","sector":"BioPharma","title":"Environmental Monitoring Exceedance","priority":"High","status":"Draft Generated","site":"Site C - Hyderabad","owner":"M. Reddy","detectedDate":"2024-07-08","description":"Environmental monitoring in Grade B cleanroom exceeded action limits for viable particles during aseptic manufacturing campaign.","regulatoryRef":["EU GMP Annex 1","21 CFR Part 211.42","ISO 14644-1"]},
        {"id":"QR-2024-013","type":"audit","sector":"Medical Device","title":"Supplier Qualification Gap","priority":"Medium","status":"Draft Generated","site":"Site D - Bangalore","owner":"V. Rao","detectedDate":"2024-07-25","description":"External audit identified that 5 critical suppliers lack current qualification documentation.","regulatoryRef":["ISO 13485:2016 Section 7.4","21 CFR 820.50","EU MDR Article 10"]},
        {"id":"QR-2024-014","type":"cc","sector":"Medical Device","title":"Software Update - Embedded Firmware","priority":"High","status":"Draft Generated","site":"Site A - Chennai","owner":"P. Nair","detectedDate":"2024-08-10","description":"Proposed firmware update v3.2.1 for cardiac monitor to address cybersecurity vulnerability identified in v3.2.0.","regulatoryRef":["IEC 62304","21 CFR Part 820.30","EU MDR Annex I Section 17"]},
        {"id":"QR-2024-015","type":"complaint","sector":"BioPharma","title":"Stability Failure - Accelerated Study","priority":"High","status":"Draft Generated","site":"Site B - Mumbai","owner":"K. Singh","detectedDate":"2024-08-28","description":"6-month accelerated stability study results show potency degradation exceeding 5 percent specification limit for biologic product.","regulatoryRef":["ICH Q1A(R2)","21 CFR 211.166","EMA Stability Guidelines"]},
        {"id":"QR-2024-016","type":"nc","sector":"BioPharma","title":"Water System TOC Exceedance","priority":"High","status":"Draft Generated","site":"Site C - Hyderabad","owner":"D. Mehta","detectedDate":"2024-09-14","description":"Purified water system TOC results exceeded 500 ppb action limit in three consecutive daily samples from distribution loop.","regulatoryRef":["USP 643","21 CFR 211.68","EU GMP Chapter 3"]},
        {"id":"QR-2024-017","type":"deviation","sector":"Medical Device","title":"Cleanroom Gowning Procedure Deviation","priority":"Low","status":"Draft Generated","site":"Site D - Bangalore","owner":"V. Rao","detectedDate":"2024-10-02","description":"Observation of operator not following approved gowning procedure in ISO Class 7 cleanroom during routine operations.","regulatoryRef":["ISO 14644-2","21 CFR 820.20","EU MDR Annex IX"]},
        {"id":"QR-2024-018","type":"cc","sector":"BioPharma","title":"Analytical Method Change - HPLC","priority":"Medium","status":"Draft Generated","site":"Site B - Mumbai","owner":"A. Sharma","detectedDate":"2024-11-09","description":"Proposed change to HPLC analytical method for active ingredient assay to improve specificity and reduce analysis time.","regulatoryRef":["ICH Q2(R1)","USP 621","21 CFR 211.194"]},
    ]
    with SessionLocal() as db:
        if db.query(QualityRecord).count() > 0:
            return
        for r in _SEED:
            db.add(QualityRecord(
                id=r["id"], type=r["type"], sector=r["sector"],
                title=r["title"], description=r["description"],
                priority=r["priority"], status=r.get("status", "Draft Generated"),
                site=r.get("site", ""), owner=r.get("owner", ""),
                detected_date=r.get("detectedDate", ""),
                regulatory_refs=r.get("regulatoryRef", []),
                source="system", age_days=_age(r.get("detectedDate")),
            ))
        db.commit()
        log.info("records.seeded", extra={"count": len(_SEED)})


def get_all_records() -> List[Dict]:
    with SessionLocal() as db:
        return [r.to_dict() for r in
                db.query(QualityRecord)
                  .order_by(QualityRecord.created_at.desc()).all()]


def get_record_by_id(record_id: str) -> Optional[Dict]:
    with SessionLocal() as db:
        r = db.query(QualityRecord).filter(QualityRecord.id == record_id).first()
        return r.to_dict() if r else None


def get_records_by_owner(owner: str) -> List[Dict]:
    with SessionLocal() as db:
        return [r.to_dict() for r in
                db.query(QualityRecord)
                  .filter(QualityRecord.owner == owner)
                  .order_by(QualityRecord.created_at.desc()).all()]


def update_record_status(record_id: str, new_status: str) -> Optional[Dict]:
    with SessionLocal() as db:
        r = db.query(QualityRecord).filter(QualityRecord.id == record_id).first()
        if not r:
            return None
        r.status = new_status
        r.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(r)
        return r.to_dict()


def add_uploaded_record(record: Dict) -> Dict:
    with SessionLocal() as db:
        if db.query(QualityRecord).filter(QualityRecord.id == record.get("id")).first():
            record["id"] += "-" + "".join(random.choices(string.digits, k=3))
        rec = QualityRecord(
            id=record["id"],
            type=record.get("type", "complaint"),
            sector=record.get("sector", "Medical Device"),
            title=record.get("title", ""),
            description=record.get("description", ""),
            priority=record.get("priority", "Medium"),
            status=record.get("status", "Draft Generated"),
            site=record.get("site", ""),
            owner=record.get("owner", ""),
            detected_date=record.get("detectedDate", ""),
            product_family=record.get("productFamily", ""),
            batch_lot=record.get("batchLot", ""),
            regulatory_refs=record.get("regulatoryRef", []),
            source="uploaded",
            age_days=_age(record.get("detectedDate")),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.to_dict()


def upsert_external_record(record: Dict) -> Dict:
    """Create or update a quality record supplied by an external QMS."""
    from services.workflow_config import normalize_record_type

    record_id = (
        record.get("id")
        or record.get("recordId")
        or record.get("externalId")
        or record.get("caseId")
    )
    if not record_id:
        raise ValueError("External record must include id, recordId, externalId, or caseId")

    with SessionLocal() as db:
        existing = db.query(QualityRecord).filter(QualityRecord.id == record_id).first()
        if existing:
            existing.type = normalize_record_type(record.get("type") or record.get("category") or existing.type)
            existing.sector = record.get("sector", existing.sector or "Medical Device")
            existing.title = record.get("title", existing.title or "")
            existing.description = record.get("description", existing.description or "")
            existing.priority = record.get("priority", existing.priority or "Medium")
            existing.status = record.get("status", existing.status or "Draft Generated")
            existing.site = record.get("site", existing.site or "")
            existing.owner = record.get("owner") or record.get("createdBy") or existing.owner or ""
            existing.detected_date = record.get("detectedDate", existing.detected_date or "")
            existing.product_family = record.get("productFamily", existing.product_family or "")
            existing.batch_lot = record.get("batchLot", existing.batch_lot or "")
            existing.regulatory_refs = record.get("regulatoryRef", existing.regulatory_refs or [])
            existing.source = record.get("_source", "external")
            existing.age_days = _age(existing.detected_date)
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing.to_dict()

        rec = QualityRecord(
            id=record_id,
            type=normalize_record_type(record.get("type") or record.get("category") or "deviation"),
            sector=record.get("sector", "Medical Device"),
            title=record.get("title", ""),
            description=record.get("description", ""),
            priority=record.get("priority", "Medium"),
            status=record.get("status", "Draft Generated"),
            site=record.get("site", ""),
            owner=record.get("owner") or record.get("createdBy") or "",
            detected_date=record.get("detectedDate", ""),
            product_family=record.get("productFamily", ""),
            batch_lot=record.get("batchLot", ""),
            regulatory_refs=record.get("regulatoryRef", []),
            source=record.get("_source", "external"),
            age_days=_age(record.get("detectedDate")),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.to_dict()


def _c2d(c: CAPARecord) -> Dict:
    record = getattr(c, "record", None)
    return {
        "capaId":               c.capa_id,
        "sourceRecordId":       c.record_id,
        "sourceRecordType":     record.type if record else "",
        "sourceRecordTitle":    record.title if record else "",
        "sector":               record.sector if record else "",
        "priority":             record.priority if record else "",
        "rootCause":            c.root_cause or "",
        "immediateAction":      c.immediate_action or "",
        "correctiveAction":     c.corrective_action or "",
        "preventiveAction":     c.preventive_action or "",
        "capaOwner":            c.proposed_owner or "",
        "effectivenessCheck":   c.effectiveness_check or "",
        "estimatedClosureDays": c.estimated_closure_days,
        "riskRating":           c.risk_rating or "",
        "regulatoryRef":        c.regulatory_refs or [],
        "capaMetadata":         c.capa_metadata or {},
        "status":               c.status,
        "approved":             c.approved,
        "approvedBy":           c.approved_by or "",
        "rejectedBy":           c.rejected_by or "",
        "rejectedAt":           c.rejected_at.isoformat() if c.rejected_at else "",
        "rejectionComment":     c.rejection_comment or "",
        "createdByUsername":    c.created_by_username or "",
        "createdAt":            c.created_at.isoformat() if c.created_at else "",
        "updatedAt":            c.updated_at.isoformat() if c.updated_at else "",
        "rcaQualityScore":      c.rca_quality_score,
    }


def save_capa(capa: Dict) -> Dict:
    with SessionLocal() as db:
        existing = db.query(CAPARecord).filter(
            CAPARecord.capa_id == capa.get("capaId")).first()
        source_record_id = (capa.get("sourceRecordId") or "").strip()
        if existing is None and source_record_id:
            existing = db.query(CAPARecord).filter(
                CAPARecord.record_id == source_record_id,
                CAPARecord.status.in_(["Draft Generated", "Under Review", "Pending Correction"]),
            ).order_by(CAPARecord.created_at.desc()).first()
        if existing:
            existing.root_cause             = capa.get("rootCause",            existing.root_cause)
            existing.immediate_action       = capa.get("immediateAction",      existing.immediate_action)
            existing.corrective_action      = capa.get("correctiveAction",     existing.corrective_action)
            existing.preventive_action      = capa.get("preventiveAction",     existing.preventive_action)
            existing.proposed_owner         = capa.get("capaOwner",            existing.proposed_owner)
            existing.effectiveness_check    = capa.get("effectivenessCheck",   existing.effectiveness_check)
            existing.estimated_closure_days = capa.get("estimatedClosureDays", existing.estimated_closure_days)
            existing.risk_rating            = capa.get("riskRating",           existing.risk_rating)
            existing.regulatory_refs        = capa.get("regulatoryRef",        existing.regulatory_refs)
            existing.capa_metadata          = capa.get("capaMetadata",         existing.capa_metadata)
            existing.status                 = capa.get("status",               existing.status)
            existing.updated_at             = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return _c2d(existing)
        else:
            new_c = CAPARecord(
                capa_id=capa.get("capaId", ""),
                record_id=source_record_id,
                root_cause=capa.get("rootCause", ""),
                immediate_action=capa.get("immediateAction", ""),
                corrective_action=capa.get("correctiveAction", ""),
                preventive_action=capa.get("preventiveAction", ""),
                proposed_owner=capa.get("capaOwner", ""),
                effectiveness_check=capa.get("effectivenessCheck", ""),
                estimated_closure_days=capa.get("estimatedClosureDays", 90),
                risk_rating=capa.get("riskRating", "Medium"),
                regulatory_refs=capa.get("regulatoryRef", []),
                capa_metadata=capa.get("capaMetadata", {}),
                status=capa.get("status", "Under Review"),
                created_by_username=capa.get("createdByUsername", ""),
                rca_quality_score=capa.get("rcaQualityScore"),
            )
            db.add(new_c)
            db.commit()
            db.refresh(new_c)
            return _c2d(new_c)


def get_all_capas() -> List[Dict]:
    with SessionLocal() as db:
        return [_c2d(c) for c in
                db.query(CAPARecord)
                  .order_by(CAPARecord.created_at.desc()).all()]


def get_capas_by_owner(owner: str) -> List[Dict]:
    with SessionLocal() as db:
        return [_c2d(c) for c in
                db.query(CAPARecord)
                  .filter(CAPARecord.created_by_username == owner)
                  .order_by(CAPARecord.created_at.desc()).all()]


def get_capa_by_id(capa_id: str) -> Optional[Dict]:
    with SessionLocal() as db:
        c = db.query(CAPARecord).filter(CAPARecord.capa_id == capa_id).first()
        return _c2d(c) if c else None


def get_capa_by_record_id(record_id: str) -> Optional[Dict]:
    with SessionLocal() as db:
        c = db.query(CAPARecord).filter(CAPARecord.record_id == record_id).first()
        return _c2d(c) if c else None


def update_capa_status(
    capa_id: str,
    new_status: str,
    *,
    rejected_by: str = "",
    rejection_comment: str = "",
    capa_metadata: Dict = None,
) -> Optional[Dict]:
    with SessionLocal() as db:
        c = db.query(CAPARecord).filter(CAPARecord.capa_id == capa_id).first()
        if not c:
            return None
        c.status = new_status
        c.updated_at = datetime.utcnow()
        if capa_metadata is not None:
            c.capa_metadata = capa_metadata
        if new_status == "Approved":
            c.approved = True
            c.approved_at = datetime.utcnow()
            c.approved_by = rejected_by or c.approved_by
            c.rejected_by = ""
            c.rejected_at = None
            c.rejection_comment = ""
        elif new_status == "Pending Correction":
            c.approved = False
            c.rejected_by = rejected_by
            c.rejected_at = datetime.utcnow()
            c.rejection_comment = rejection_comment
        db.commit()
        db.refresh(c)
        return _c2d(c)


def search_records(query: str,
                   # --- route/search.py calls with these args ---
                   username: str = "",
                   sees_all: bool = True,
                   # --- search page calls with these args ---
                   scope: str = "all",
                   type_filter: str = "",
                   priority_filter: str = "",
                   status_filter: str = "") -> List[Dict]:
    """
    Unified search — works with BOTH calling signatures:
      routes/search.py  → search_records(q, username=x, sees_all=True)
      search page       → search_records(q, scope="all", type_filter=x)
    Returns a list of record dicts with _score field.
    """
    q = query.lower().strip()
    if not q:
        return []

    with SessionLocal() as db:
        records = db.query(QualityRecord).all()

        # Apply role filter
        if not sees_all and username:
            records = [r for r in records if r.owner == username]

        # Apply field filters
        if type_filter:
            records = [r for r in records if r.type == type_filter]
        if priority_filter:
            records = [r for r in records if r.priority == priority_filter]
        if status_filter:
            records = [r for r in records if r.status == status_filter]

        hits = []
        for rec in records:
            score = 0
            matched = []
            fields = [
                ("id",          rec.id,          10),
                ("title",       rec.title,        8),
                ("description", rec.description,  5),
                ("owner",       rec.owner,        4),
                ("site",        rec.site,         3),
                ("type",        rec.type,         3),
                ("sector",      rec.sector,       3),
                ("priority",    rec.priority,     2),
                ("status",      rec.status,       2),
            ]
            for field, value, weight in fields:
                if value and q in str(value).lower():
                    score += weight
                    matched.append(field)
            for ref in (rec.regulatory_refs or []):
                if q in ref.lower():
                    score += 4
                    if "regulatoryRef" not in matched:
                        matched.append("regulatoryRef")
            if score > 0:
                d = rec.to_dict()
                d["_score"] = score
                d["_searchScore"] = score
                d["_matchedFields"] = matched
                hits.append(d)

        hits.sort(key=lambda x: x["_score"], reverse=True)
        return hits


def log_action(username: str, action: str, entity_type: str = "",
               entity_id: str = "", record_id: str = None,
               detail: str = "", ip_address: str = "", ai_provider: str = ""):
    with SessionLocal() as db:
        db.add(AuditLog(
            username=username, action=action,
            entity_type=entity_type, entity_id=entity_id,
            record_id=record_id, detail=detail,
            ip_address=ip_address, ai_provider=ai_provider,
        ))
        db.commit()


def get_audit_logs(limit: int = 100) -> List[Dict]:
    with SessionLocal() as db:
        return [l.to_dict() for l in
                db.query(AuditLog)
                  .order_by(AuditLog.timestamp.desc())
                  .limit(limit).all()]
