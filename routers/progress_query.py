from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta

from database import get_db
from models import ClaimCase, ClaimStatus, SupplementItem, CallLog, RiskLevel
from schemas import ProgressResponse, SupplementItemResponse, CallLogResponse

router = APIRouter(prefix="/api/progress", tags=["进度查询"])

STATUS_DESCRIPTIONS = {
    ClaimStatus.SUBMITTED: "案件已提交，等待处理",
    ClaimStatus.OCR_PROCESSING: "正在进行图片识别(OCR)",
    ClaimStatus.OCR_COMPLETED: "图片识别完成",
    ClaimStatus.EXTRACTION_PROCESSING: "正在进行文本信息抽取",
    ClaimStatus.EXTRACTION_COMPLETED: "文本信息抽取完成",
    ClaimStatus.RULE_CHECKING: "正在进行规则核对",
    ClaimStatus.RULE_CHECKED: "规则核对完成",
    ClaimStatus.RISK_ANALYZING: "正在进行风险分析",
    ClaimStatus.RISK_ANALYZED: "风险分析完成",
    ClaimStatus.PENDING_REVIEW: "等待人工复核",
    ClaimStatus.REVIEWING: "正在人工复核",
    ClaimStatus.REVIEWED: "人工复核完成",
    ClaimStatus.SUPPLEMENT_REQUESTED: "需要补充材料",
    ClaimStatus.APPROVED: "审核通过，等待赔付",
    ClaimStatus.REJECTED: "审核拒绝",
    ClaimStatus.WITHDRAWN: "已撤回",
    ClaimStatus.COMPLETED: "案件处理完成"
}

STATUS_ORDER = [
    ClaimStatus.SUBMITTED,
    ClaimStatus.OCR_PROCESSING,
    ClaimStatus.OCR_COMPLETED,
    ClaimStatus.EXTRACTION_PROCESSING,
    ClaimStatus.EXTRACTION_COMPLETED,
    ClaimStatus.RULE_CHECKING,
    ClaimStatus.RULE_CHECKED,
    ClaimStatus.RISK_ANALYZING,
    ClaimStatus.RISK_ANALYZED,
    ClaimStatus.PENDING_REVIEW,
    ClaimStatus.REVIEWING,
    ClaimStatus.REVIEWED,
    ClaimStatus.SUPPLEMENT_REQUESTED,
    ClaimStatus.APPROVED,
    ClaimStatus.REJECTED,
    ClaimStatus.WITHDRAWN,
    ClaimStatus.COMPLETED
]


@router.get("/case/{case_id}", response_model=ProgressResponse)
def get_case_progress(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    current_step = STATUS_ORDER.index(case.status) + 1
    total_steps = len(STATUS_ORDER)

    processing_steps = 10
    processing_current = min(current_step, processing_steps)
    progress_percent = (processing_current / processing_steps) * 100

    estimated_completion = None
    if case.status not in [ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.COMPLETED, ClaimStatus.WITHDRAWN]:
        remaining_steps = processing_steps - processing_current
        estimated_completion = datetime.utcnow() + timedelta(minutes=remaining_steps * 5)

    timeline = []
    for i, status in enumerate(STATUS_ORDER[:current_step]):
        timeline.append({
            "step": i + 1,
            "status": status.value,
            "description": STATUS_DESCRIPTIONS.get(status, status.value),
            "completed": True,
            "timestamp": case.created_at + timedelta(minutes=i * 2)
        })

    for i, status in enumerate(STATUS_ORDER[current_step:]):
        timeline.append({
            "step": current_step + i + 1,
            "status": status.value,
            "description": STATUS_DESCRIPTIONS.get(status, status.value),
            "completed": False,
            "timestamp": None
        })

    supplement_items = db.query(SupplementItem).filter(
        SupplementItem.case_id == case_id
    ).order_by(SupplementItem.priority, SupplementItem.created_at).all()

    return ProgressResponse(
        case_id=case.id,
        case_no=case.case_no,
        status=case.status,
        status_description=STATUS_DESCRIPTIONS.get(case.status, case.status.value if case.status else "unknown"),
        current_step=processing_current,
        total_steps=processing_steps,
        progress_percent=round(progress_percent, 2),
        estimated_completion_time=estimated_completion,
        supplement_items=supplement_items,
        timeline=timeline
    )


@router.get("/case/{case_id}/supplements", response_model=list[SupplementItemResponse])
def get_supplement_list(
    case_id: int,
    is_completed: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    query = db.query(SupplementItem).filter(SupplementItem.case_id == case_id)

    if is_completed is not None:
        query = query.filter(SupplementItem.is_completed == is_completed)

    return query.order_by(SupplementItem.priority, SupplementItem.created_at).all()


@router.get("/case/{case_id}/logs", response_model=list[CallLogResponse])
def get_case_call_logs(
    case_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    logs = db.query(CallLog).filter(
        CallLog.case_id == case_id
    ).order_by(CallLog.created_at.desc()).offset(skip).limit(limit).all()

    return logs


@router.get("/list", response_model=list)
def list_cases(
    status: Optional[ClaimStatus] = None,
    risk_level: Optional[RiskLevel] = None,
    is_high_risk: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(ClaimCase)

    if status is not None:
        query = query.filter(ClaimCase.status == status)
    if risk_level is not None:
        query = query.filter(ClaimCase.risk_level == risk_level)
    if is_high_risk is not None:
        query = query.filter(ClaimCase.is_high_risk == is_high_risk)

    cases = query.order_by(ClaimCase.updated_at.desc()).offset(skip).limit(limit).all()

    result = []
    for case in cases:
        progress = get_case_progress_obj(case)
        result.append({
            "case_id": case.id,
            "case_no": case.case_no,
            "claimant_name": case.claimant_name,
            "claim_amount": case.claim_amount,
            "risk_level": case.risk_level.value if case.risk_level else "low",
            "risk_score": case.risk_score or 0,
            "is_high_risk": case.is_high_risk or False,
            "status": case.status.value if case.status else "unknown",
            "status_description": STATUS_DESCRIPTIONS.get(case.status, case.status.value if case.status else "unknown"),
            "progress_percent": progress["progress_percent"],
            "current_step": progress["current_step"],
            "total_steps": progress["total_steps"],
            "updated_at": case.updated_at
        })

    return result


@router.get("/status/{status}", response_model=list)
def get_cases_by_status(
    status: ClaimStatus,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    cases = db.query(ClaimCase).filter(
        ClaimCase.status == status
    ).order_by(ClaimCase.updated_at.desc()).offset(skip).limit(limit).all()

    result = []
    for case in cases:
        progress = get_case_progress_obj(case)
        result.append({
            "case_id": case.id,
            "case_no": case.case_no,
            "claimant_name": case.claimant_name,
            "claim_amount": case.claim_amount,
            "risk_level": case.risk_level.value if case.risk_level else "low",
            "risk_score": case.risk_score or 0,
            "is_high_risk": case.is_high_risk or False,
            "status": case.status.value if case.status else "unknown",
            "status_description": STATUS_DESCRIPTIONS.get(case.status, case.status.value if case.status else "unknown"),
            "progress_percent": progress["progress_percent"],
            "current_step": progress["current_step"],
            "total_steps": progress["total_steps"],
            "updated_at": case.updated_at
        })

    return result


def get_case_progress_obj(case: ClaimCase) -> dict:
    if not case.status or case.status not in STATUS_ORDER:
        current_step = 0
    else:
        current_step = STATUS_ORDER.index(case.status) + 1
    processing_steps = 10
    processing_current = min(current_step, processing_steps)
    progress_percent = (processing_current / processing_steps) * 100

    return {
        "progress_percent": round(progress_percent, 2),
        "current_step": processing_current,
        "total_steps": processing_steps
    }


@router.get("/case/{case_id}/supplement-list")
def generate_supplement_list(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    supplement_items = db.query(SupplementItem).filter(
        SupplementItem.case_id == case_id,
        SupplementItem.is_completed == False
    ).order_by(SupplementItem.priority, SupplementItem.created_at).all()

    items_list = []
    for item in supplement_items:
        items_list.append({
            "priority": "高" if item.priority == 1 else "中" if item.priority == 2 else "低",
            "item_name": item.item_name,
            "description": item.description,
            "reason": item.reason
        })

    return {
        "case_no": case.case_no,
        "claimant_name": case.claimant_name,
        "generated_at": datetime.utcnow(),
        "supplement_notes": case.supplement_notes,
        "items_count": len(items_list),
        "items": items_list,
        "deadline": datetime.utcnow() + timedelta(days=7)
    }
