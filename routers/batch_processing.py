from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from database import get_db
from models import (
    ClaimCase, ClaimStatus, BatchTask, BatchTaskStatus, BatchTaskType,
    OCRResult, ExtractedData, RuleCheckResult, RiskAlert, Document,
    SupplementItem, RiskLevel
)
from schemas import BatchProcessRequest, BatchTaskResponse, BatchCaseResult
from mock_ai_service import MockOCRService, MockNLPService, MockRuleEngine, MockRiskAnalyzer
from config import settings

router = APIRouter(prefix="/api/batch", tags=["批量处理"])


def generate_task_no() -> str:
    return f"BATCH{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


@router.post("/process", response_model=BatchTaskResponse)
async def batch_process(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    query = db.query(ClaimCase)

    if request.case_ids and len(request.case_ids) > 0:
        query = query.filter(ClaimCase.id.in_(request.case_ids))
    elif request.status_filter is not None:
        query = query.filter(ClaimCase.status == request.status_filter)
    else:
        query = query.filter(ClaimCase.status.in_([
            ClaimStatus.SUBMITTED,
            ClaimStatus.OCR_COMPLETED,
            ClaimStatus.EXTRACTION_COMPLETED
        ]))

    cases = query.order_by(ClaimCase.created_at.asc()).all()
    if not cases:
        raise HTTPException(status_code=400, detail="没有符合条件的案件")

    task = BatchTask(
        task_no=generate_task_no(),
        task_type=request.task_type,
        status=BatchTaskStatus.PENDING,
        triggered_by=request.triggered_by,
        filter_status=request.status_filter.value if request.status_filter else None,
        case_ids=[c.id for c in cases],
        total_count=len(cases)
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(
        run_batch_task,
        task.id,
        request.task_type,
        [c.id for c in cases],
        db.bind.url
    )

    return BatchTaskResponse(
        task_id=task.id,
        task_no=task.task_no,
        task_type=task.task_type,
        status=task.status,
        total_count=task.total_count,
        success_count=0,
        failed_count=0,
        results=[]
    )


@router.get("/task/{task_id}", response_model=BatchTaskResponse)
def get_batch_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(BatchTask).filter(BatchTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="批量任务不存在")

    results = []
    for r in task.results or []:
        results.append(BatchCaseResult(**r))

    return BatchTaskResponse(
        task_id=task.id,
        task_no=task.task_no,
        task_type=task.task_type,
        status=task.status,
        total_count=task.total_count,
        success_count=task.success_count,
        failed_count=task.failed_count,
        results=results,
        started_at=task.started_at,
        completed_at=task.completed_at
    )


@router.get("/tasks", response_model=List[BatchTaskResponse])
def list_batch_tasks(
    status: Optional[BatchTaskStatus] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(BatchTask)
    if status is not None:
        query = query.filter(BatchTask.status == status)
    tasks = query.order_by(BatchTask.created_at.desc()).offset(skip).limit(limit).all()

    resp = []
    for task in tasks:
        results = []
        for r in task.results or []:
            results.append(BatchCaseResult(**r))
        resp.append(BatchTaskResponse(
            task_id=task.id,
            task_no=task.task_no,
            task_type=task.task_type,
            status=task.status,
            total_count=task.total_count,
            success_count=task.success_count,
            failed_count=task.failed_count,
            results=results,
            started_at=task.started_at,
            completed_at=task.completed_at
        ))
    return resp


def run_batch_task(task_id: int, task_type: BatchTaskType, case_ids: List[int], db_url):
    from database import SessionLocal
    db = SessionLocal()

    try:
        task = db.query(BatchTask).filter(BatchTask.id == task_id).first()
        if not task:
            return

        task.status = BatchTaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        db.commit()

        results = []
        success_count = 0
        failed_count = 0

        for case_id in case_ids:
            case_result = process_single_case(db, case_id, task_type)
            results.append(case_result.model_dump())
            if case_result.success:
                success_count += 1
            else:
                failed_count += 1

        task.status = BatchTaskStatus.COMPLETED
        task.success_count = success_count
        task.failed_count = failed_count
        task.results = results
        task.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        db.rollback()
        if task:
            task.status = BatchTaskStatus.FAILED
            task.extra_data = {"error": str(e)}
            db.commit()
    finally:
        db.close()


def process_single_case(db: Session, case_id: int, task_type: BatchTaskType) -> BatchCaseResult:
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        return BatchCaseResult(
            case_id=case_id,
            case_no="UNKNOWN",
            success=False,
            message="案件不存在",
            stage="init",
            error_type="case_not_found"
        )

    current_stage = "init"
    try:
        stages_needed = []
        if task_type == BatchTaskType.OCR:
            stages_needed = ["ocr"]
        elif task_type == BatchTaskType.EXTRACTION:
            stages_needed = ["ocr", "extraction"]
        elif task_type == BatchTaskType.RULE_CHECK:
            stages_needed = ["ocr", "extraction", "rule_check"]
        elif task_type == BatchTaskType.RISK_ANALYSIS:
            stages_needed = ["ocr", "extraction", "rule_check", "risk_analysis"]
        else:
            stages_needed = ["ocr", "extraction", "rule_check", "risk_analysis"]

        for stage in stages_needed:
            current_stage = stage
            if stage == "ocr":
                if case.status not in [ClaimStatus.SUBMITTED, ClaimStatus.OCR_PROCESSING]:
                    continue
                run_ocr_for_case(db, case)
            elif stage == "extraction":
                if case.status not in [ClaimStatus.OCR_COMPLETED, ClaimStatus.EXTRACTION_PROCESSING, ClaimStatus.SUBMITTED]:
                    if case.status == ClaimStatus.SUBMITTED:
                        run_ocr_for_case(db, case)
                    else:
                        continue
                run_extraction_for_case(db, case)
            elif stage == "rule_check":
                if case.status not in [ClaimStatus.EXTRACTION_COMPLETED, ClaimStatus.RULE_CHECKING, ClaimStatus.OCR_COMPLETED, ClaimStatus.SUBMITTED]:
                    if case.status in [ClaimStatus.SUBMITTED, ClaimStatus.OCR_COMPLETED]:
                        if case.status == ClaimStatus.SUBMITTED:
                            run_ocr_for_case(db, case)
                        run_extraction_for_case(db, case)
                    else:
                        continue
                run_rule_check_for_case(db, case)
            elif stage == "risk_analysis":
                if case.status not in [ClaimStatus.RULE_CHECKED, ClaimStatus.RISK_ANALYZING, ClaimStatus.EXTRACTION_COMPLETED, ClaimStatus.OCR_COMPLETED, ClaimStatus.SUBMITTED]:
                    if case.status in [ClaimStatus.SUBMITTED, ClaimStatus.OCR_COMPLETED, ClaimStatus.EXTRACTION_COMPLETED]:
                        if case.status == ClaimStatus.SUBMITTED:
                            run_ocr_for_case(db, case)
                        if case.status in [ClaimStatus.SUBMITTED, ClaimStatus.OCR_COMPLETED]:
                            run_extraction_for_case(db, case)
                        run_rule_check_for_case(db, case)
                    else:
                        continue
                run_risk_analysis_for_case(db, case)

        db.commit()
        db.refresh(case)
        return BatchCaseResult(
            case_id=case.id,
            case_no=case.case_no,
            success=True,
            message=f"处理完成，当前状态: {case.status.value if case.status else 'unknown'}",
            stage="completed",
            final_status=case.status.value if case.status else "unknown"
        )

    except Exception as e:
        db.rollback()
        db.refresh(case)
        return BatchCaseResult(
            case_id=case.id,
            case_no=case.case_no,
            success=False,
            message=f"处理失败: {str(e)}",
            stage=current_stage,
            error_type=type(e).__name__,
            error_detail=str(e),
            final_status=case.status.value if case.status else "unknown"
        )


def run_ocr_for_case(db: Session, case: ClaimCase):
    case.status = ClaimStatus.OCR_PROCESSING
    db.commit()

    documents = db.query(Document).filter(Document.case_id == case.id).all()
    db.query(OCRResult).filter(OCRResult.case_id == case.id).delete()

    for doc in documents:
        doc_type = doc.document_type.value if doc.document_type else "unknown"
        ocr_result = MockOCRService.recognize(doc_type, doc.file_path, doc.file_name)
        result = OCRResult(
            case_id=case.id,
            document_id=doc.id,
            recognized_text=ocr_result["recognized_text"],
            confidence=ocr_result["confidence"],
            recognized_amount=ocr_result.get("recognized_amount"),
            recognized_date=ocr_result.get("recognized_date"),
            recognized_name=ocr_result.get("recognized_name"),
            recognized_id_card=ocr_result.get("recognized_id_card"),
            invoice_no=ocr_result.get("invoice_no"),
            hospital_name=ocr_result.get("hospital_name"),
            diagnosis=ocr_result.get("diagnosis"),
            processing_time_ms=ocr_result.get("processing_time_ms")
        )
        db.add(result)
        doc.ocr_completed = True

    case.status = ClaimStatus.OCR_COMPLETED
    db.commit()


def run_extraction_for_case(db: Session, case: ClaimCase):
    case.status = ClaimStatus.EXTRACTION_PROCESSING
    db.commit()

    ocr_results = db.query(OCRResult).filter(OCRResult.case_id == case.id).all()

    db.query(ExtractedData).filter(ExtractedData.case_id == case.id).delete()

    for ocr_result in ocr_results:
        document = ocr_result.document
        extracted_items = MockNLPService.extract(
            ocr_text=ocr_result.recognized_text or "",
            document_type=document.document_type.value if document else "unknown"
        )
        for item in extracted_items:
            ed = ExtractedData(
                case_id=case.id,
                source_type=item.get("source_type", "ocr"),
                key=item["key"],
                value=str(item.get("value", "")),
                value_type=item.get("value_type", "string"),
                confidence=item.get("confidence", 0.8),
                extracted_from=f"ocr_result_{ocr_result.id}:{item.get('extracted_from', '')}"
            )
            db.add(ed)

    case.status = ClaimStatus.EXTRACTION_COMPLETED
    db.commit()


def run_rule_check_for_case(db: Session, case: ClaimCase):
    case.status = ClaimStatus.RULE_CHECKING
    db.commit()

    ocr_results = db.query(OCRResult).filter(OCRResult.case_id == case.id).all()
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

    db.query(RuleCheckResult).filter(RuleCheckResult.case_id == case.id).delete()
    db.query(SupplementItem).filter(
        SupplementItem.case_id == case.id,
        SupplementItem.is_completed == False
    ).delete()

    for rule in rule_results:
        check_result = RuleCheckResult(
            case_id=case.id,
            rule_code=rule["rule_code"],
            rule_name=rule["rule_name"],
            passed=rule["passed"],
            actual_value=rule["actual_value"],
            expected_value=rule["expected_value"],
            description=rule["description"],
            severity=rule["severity"],
            suggestion=rule.get("suggestion")
        )
        db.add(check_result)

    failed_error_rules = [r for r in rule_results if not r["passed"] and r["severity"] == "error"]
    for rule in failed_error_rules:
        if rule["rule_code"] == "RULE_005":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_001", item_name="医疗发票",
                description="请上传医疗费用发票原件", reason="缺少必要的医疗发票材料", priority=1))
        elif rule["rule_code"] == "RULE_006":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_002", item_name="身份证明",
                description="请上传被保险人身份证正反面", reason="缺少身份证明材料", priority=1))
        elif rule["rule_code"] == "RULE_002":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_003", item_name="有效身份证明",
                description="请重新上传清晰有效的身份证照片", reason="身份证号格式不正确", priority=2))
        elif rule["rule_code"] == "RULE_008":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_006", item_name="身份信息核对",
                description="OCR识别姓名与提交信息不一致，请核对并补充上传清晰的身份证件",
                reason=rule.get("actual_value", "OCR识别姓名与提交信息不一致"), priority=1))
        elif rule["rule_code"] == "RULE_009":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_007", item_name="证件信息核对",
                description="OCR识别证件号与提交信息不一致，请核对并补充上传清晰的身份证件",
                reason=rule.get("actual_value", "OCR识别证件号与提交信息不一致"), priority=1))
        elif rule["rule_code"] == "RULE_010":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_008", item_name="身份信息复核",
                description="文本抽取姓名与提交信息不一致，建议人工复核",
                reason=rule.get("actual_value", "文本抽取姓名与提交信息不一致"), priority=2))
        elif rule["rule_code"] == "RULE_011":
            db.add(SupplementItem(case_id=case.id, item_code="SUP_009", item_name="证件信息复核",
                description="文本抽取证件号与提交信息不一致，建议人工复核",
                reason=rule.get("actual_value", "文本抽取证件号与提交信息不一致"), priority=2))

    case.status = ClaimStatus.RULE_CHECKED
    db.commit()


def run_risk_analysis_for_case(db: Session, case: ClaimCase):
    case.status = ClaimStatus.RISK_ANALYZING
    db.commit()

    extracted_data = case.extracted_data
    rule_checks = case.rule_checks
    documents = case.documents
    ocr_results = case.ocr_results

    case_data = {
        "claim_amount": case.claim_amount,
        "claimant_name": case.claimant_name,
        "claimant_id_card": case.claimant_id_card,
        "accident_date": case.accident_date,
        "document_count": len(documents)
    }

    rule_data_list = []
    for rc in rule_checks:
        rule_data_list.append({
            "rule_code": rc.rule_code,
            "rule_name": rc.rule_name,
            "passed": rc.passed,
            "severity": rc.severity,
            "actual_value": rc.actual_value,
            "expected_value": rc.expected_value,
            "description": rc.description,
            "suggestion": rc.suggestion,
            "manual_status": rc.manual_status.value if rc.manual_status else "unconfirmed",
            "manual_note": rc.manual_note
        })

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

    historical_cases = []
    id_card = case.claimant_id_card or case.insured_id_card
    if id_card:
        cutoff_date = datetime.utcnow() - timedelta(days=365)
        history = db.query(ClaimCase).filter(
            ClaimCase.id != case.id,
            (ClaimCase.claimant_id_card == id_card) | (ClaimCase.insured_id_card == id_card),
        ).all()
        for hc in history:
            historical_cases.append({
                "case_no": hc.case_no,
                "claim_amount": hc.claim_amount,
                "claim_date": hc.claim_date,
                "status": hc.status.value if hc.status else "unknown"
            })

    db.query(RiskAlert).filter(RiskAlert.case_id == case.id).delete()

    analysis_result = MockRiskAnalyzer.analyze(case_data, rule_data_list, ocr_data_list, historical_cases)

    for alert in analysis_result["risk_alerts"]:
        risk_alert = RiskAlert(
            case_id=case.id,
            alert_code=alert["alert_code"],
            alert_type=alert.get("alert_type"),
            title=alert["title"],
            description=alert.get("description"),
            risk_level=RiskLevel(alert["risk_level"]),
            risk_score_contribution=alert.get("risk_score_contribution", 0.0),
            evidence=alert.get("evidence", {}),
            explanation=alert.get("explanation"),
            recommendation=alert.get("recommendation")
        )
        db.add(risk_alert)

    confirmed_false_positive_count = sum(
        1 for rc in rule_checks
        if not rc.passed and rc.manual_status and rc.manual_status.value == "false_positive"
    )

    case.risk_level = RiskLevel(analysis_result["overall_risk_level"])
    case.risk_score = analysis_result["overall_risk_score"]
    case.is_high_risk = analysis_result["is_high_risk"]

    if confirmed_false_positive_count > 0 and case.risk_score > 0:
        case.risk_score = max(0, case.risk_score - (confirmed_false_positive_count * 5))
        if case.risk_score < 30:
            case.risk_level = RiskLevel.LOW
            case.is_high_risk = False

    effective_failed_count = sum(
        1 for rc in rule_checks
        if not rc.passed and (not rc.manual_status or rc.manual_status.value in ["unconfirmed", "confirmed", "need_supplement"])
    )

    all_error_rules_passed = all(
        rc.passed for rc in rule_checks
        if rc.severity == "error" and (not rc.manual_status or rc.manual_status.value != "false_positive")
    )

    if case.is_high_risk or effective_failed_count > 0 or not all_error_rules_passed:
        case.status = ClaimStatus.PENDING_REVIEW
    else:
        case.status = ClaimStatus.RISK_ANALYZED
    db.commit()
