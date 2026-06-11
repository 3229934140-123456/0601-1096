from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import asyncio
from datetime import datetime, timedelta
import hashlib

from database import get_db
from models import ClaimCase, OCRResult, RuleCheckResult, ClaimStatus, Document, SupplementItem
from schemas import RuleCheckRequest, RuleCheckResponse, RuleCheckResponse as RuleCheckResp, SupplementItemResponse
from mock_ai_service import MockRuleEngine
from config import settings

router = APIRouter(prefix="/api/rules", tags=["规则核对"])


@router.post("/check", response_model=RuleCheckResponse)
async def check_rules(request: RuleCheckRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    case.status = ClaimStatus.RULE_CHECKING
    db.commit()

    try:
        await asyncio.sleep(0.1)

        ocr_results = db.query(OCRResult).filter(OCRResult.case_id == request.case_id).all()
        extracted_data = case.extracted_data

        case_data = {
            "case_no": case.case_no,
            "policy_no": case.policy_no,
            "claimant_name": case.claimant_name,
            "claimant_id_card": case.claimant_id_card,
            "insured_name": case.insured_name,
            "insured_id_card": case.insured_id_card,
            "claim_amount": case.claim_amount,
            "accident_date": case.accident_date
        }

        ocr_data_list = []
        for ocr in ocr_results:
            doc = ocr.document
            ocr_data_list.append({
                "document_type": doc.document_type.value if doc else "unknown",
                "recognized_text": ocr.recognized_text,
                "recognized_amount": ocr.recognized_amount,
                "recognized_date": ocr.recognized_date,
                "recognized_name": ocr.recognized_name,
                "recognized_id_card": ocr.recognized_id_card,
                "invoice_no": ocr.invoice_no,
                "hospital_name": ocr.hospital_name,
                "diagnosis": ocr.diagnosis
            })

        extracted_data_list = []
        for ed in extracted_data:
            extracted_data_list.append({
                "key": ed.key,
                "value": ed.value,
                "value_type": ed.value_type,
                "confidence": ed.confidence
            })

        rule_results = MockRuleEngine.check_rules(case_data, extracted_data_list, ocr_data_list)

        db.query(RuleCheckResult).filter(RuleCheckResult.case_id == request.case_id).delete()

        saved_results = []
        for rule in rule_results:
            check_result = RuleCheckResult(
                case_id=request.case_id,
                rule_code=rule["rule_code"],
                rule_name=rule["rule_name"],
                passed=rule["passed"],
                actual_value=rule["actual_value"],
                expected_value=rule["expected_value"],
                description=rule["description"],
                severity=rule["severity"]
            )
            db.add(check_result)
            saved_results.append(check_result)

        await detect_duplicate_documents(request.case_id, db)

        await generate_supplement_items(request.case_id, rule_results, ocr_data_list, db)

        all_passed = all(r["passed"] for r in rule_results if r["severity"] == "error")

        case.status = ClaimStatus.RULE_CHECKED
        db.commit()

        for result in saved_results:
            db.refresh(result)

        return RuleCheckResponse(
            success=True,
            message=f"规则核对完成，通过{sum(1 for r in rule_results if r['passed'])}/{len(rule_results)}项",
            rule_checks=saved_results,
            all_passed=all_passed
        )

    except Exception as e:
        db.rollback()
        case.status = ClaimStatus.EXTRACTION_COMPLETED
        db.commit()
        raise HTTPException(status_code=500, detail=f"规则核对失败: {str(e)}")


async def detect_duplicate_documents(case_id: int, db: Session):
    documents = db.query(Document).filter(Document.case_id == case_id).all()

    cutoff_date = datetime.utcnow() - timedelta(days=settings.DUPLICATE_DETECTION_WINDOW_DAYS)

    for doc in documents:
        if not doc.file_hash:
            continue

        dup_in_case = db.query(Document).filter(
            Document.case_id != case_id,
            Document.file_hash == doc.file_hash,
            Document.upload_time >= cutoff_date
        ).first()

        if dup_in_case:
            doc.is_duplicate = True
            doc.duplicate_with = dup_in_case.id


async def generate_supplement_items(case_id: int, rule_results, ocr_data_list, db: Session):
    db.query(SupplementItem).filter(
        SupplementItem.case_id == case_id,
        SupplementItem.is_completed == False
    ).delete()

    failed_error_rules = [r for r in rule_results if not r["passed"] and r["severity"] == "error"]

    for rule in failed_error_rules:
        if rule["rule_code"] == "RULE_005":
            item = SupplementItem(
                case_id=case_id,
                item_code="SUP_001",
                item_name="医疗发票",
                description="请上传医疗费用发票原件",
                reason="缺少必要的医疗发票材料",
                priority=1
            )
            db.add(item)
        elif rule["rule_code"] == "RULE_006":
            item = SupplementItem(
                case_id=case_id,
                item_code="SUP_002",
                item_name="身份证明",
                description="请上传被保险人身份证正反面",
                reason="缺少身份证明材料",
                priority=1
            )
            db.add(item)
        elif rule["rule_code"] == "RULE_002":
            item = SupplementItem(
                case_id=case_id,
                item_code="SUP_003",
                item_name="有效身份证明",
                description="请重新上传清晰有效的身份证照片",
                reason="身份证号格式不正确",
                priority=2
            )
            db.add(item)

    failed_warning_rules = [r for r in rule_results if not r["passed"] and r["severity"] == "warning"]

    for rule in failed_warning_rules:
        if rule["rule_code"] == "RULE_004":
            item = SupplementItem(
                case_id=case_id,
                item_code="SUP_004",
                item_name="保单复印件",
                description="请上传保险单正本复印件",
                reason="保单号未提供或无法识别",
                priority=2
            )
            db.add(item)
        elif rule["rule_code"] == "RULE_003":
            item = SupplementItem(
                case_id=case_id,
                item_code="SUP_005",
                item_name="费用明细说明",
                description="请提供索赔金额与票据金额差异的说明或补充票据",
                reason="索赔金额与票据总金额差异较大",
                priority=2
            )
            db.add(item)


@router.get("/case/{case_id}/results", response_model=List[RuleCheckResp])
def get_rule_check_results(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.rule_checks


@router.get("/case/{case_id}/supplements", response_model=List[SupplementItemResponse])
def get_supplement_items(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.supplement_items
