from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import ClaimCase, Reviewer, ReviewRecord, SupplementItem, ClaimStatus, ReviewResult
from schemas import (
    AssignReviewerRequest, ReviewSubmitRequest, WithdrawCaseRequest,
    ReviewerResponse, ReviewRecordResponse, SupplementItemResponse, CaseResponse
)

router = APIRouter(prefix="/api/review", tags=["人工复核"])


@router.post("/reviewers", response_model=ReviewerResponse)
def create_reviewer(
    employee_no: str,
    name: str,
    department: Optional[str] = None,
    level: str = "junior",
    db: Session = Depends(get_db)
):
    existing = db.query(Reviewer).filter(Reviewer.employee_no == employee_no).first()
    if existing:
        raise HTTPException(status_code=400, detail="员工号已存在")

    reviewer = Reviewer(
        employee_no=employee_no,
        name=name,
        department=department,
        level=level
    )

    db.add(reviewer)
    db.commit()
    db.refresh(reviewer)

    return reviewer


@router.get("/reviewers", response_model=List[ReviewerResponse])
def list_reviewers(
    is_active: Optional[bool] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Reviewer)

    if is_active is not None:
        query = query.filter(Reviewer.is_active == is_active)
    if department:
        query = query.filter(Reviewer.department == department)

    return query.all()


@router.post("/assign", response_model=CaseResponse)
def assign_reviewer(request: AssignReviewerRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    reviewer = db.query(Reviewer).filter(
        Reviewer.id == request.reviewer_id,
        Reviewer.is_active == True
    ).first()
    if not reviewer:
        raise HTTPException(status_code=404, detail="复核人不存在或未激活")

    case.reviewer_id = request.reviewer_id
    case.status = ClaimStatus.REVIEWING

    review_record = ReviewRecord(
        case_id=request.case_id,
        reviewer_id=request.reviewer_id,
        action="assign",
        opinion=f"案件分派给复核人: {reviewer.name}"
    )
    db.add(review_record)

    db.commit()
    db.refresh(case)

    return case


@router.post("/submit", response_model=CaseResponse)
def submit_review(request: ReviewSubmitRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if not case.reviewer_id:
        raise HTTPException(status_code=400, detail="案件尚未分派复核人")

    review_record = ReviewRecord(
        case_id=request.case_id,
        reviewer_id=case.reviewer_id,
        action="review_submit",
        opinion=request.opinion,
        result=request.result,
        approved_amount=request.approved_amount
    )
    db.add(review_record)

    case.review_result = request.result
    case.review_opinion = request.opinion
    case.review_date = datetime.utcnow()
    case.final_approved_amount = request.approved_amount
    case.status = ClaimStatus.REVIEWED

    if request.result == ReviewResult.NEED_SUPPLEMENT:
        case.status = ClaimStatus.SUPPLEMENT_REQUESTED
        case.supplement_notes = request.opinion

        for item in request.supplement_items:
            sup_item = SupplementItem(
                case_id=request.case_id,
                item_code=item.item_code,
                item_name=item.item_name,
                description=item.description,
                reason=item.reason,
                priority=item.priority
            )
            db.add(sup_item)

    elif request.result == ReviewResult.APPROVED:
        case.status = ClaimStatus.APPROVED

    elif request.result == ReviewResult.REJECTED:
        case.status = ClaimStatus.REJECTED

    db.commit()
    db.refresh(case)

    return case


@router.post("/withdraw", response_model=CaseResponse)
def withdraw_case(request: WithdrawCaseRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.reviewer_id:
        review_record = ReviewRecord(
            case_id=request.case_id,
            reviewer_id=case.reviewer_id,
            action="withdraw",
            opinion=f"撤回重审，原因: {request.reason or '未说明'}"
        )
        db.add(review_record)

    case.status = ClaimStatus.SUBMITTED
    case.reviewer_id = None
    case.review_result = None
    case.review_opinion = None
    case.review_date = None
    case.final_approved_amount = None

    db.query(SupplementItem).filter(
        SupplementItem.case_id == request.case_id,
        SupplementItem.is_completed == False
    ).delete()

    db.commit()
    db.refresh(case)

    return case


@router.post("/{case_id}/supplement/{item_id}/complete")
def complete_supplement_item(
    case_id: int,
    item_id: int,
    db: Session = Depends(get_db)
):
    item = db.query(SupplementItem).filter(
        SupplementItem.id == item_id,
        SupplementItem.case_id == case_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="补件项目不存在")

    item.is_completed = True
    item.completed_at = datetime.utcnow()

    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if case:
        pending_items = db.query(SupplementItem).filter(
            SupplementItem.case_id == case_id,
            SupplementItem.is_completed == False
        ).count()

        if pending_items == 0:
            case.status = ClaimStatus.PENDING_REVIEW

    db.commit()
    db.refresh(item)

    return {"success": True, "message": "补件项目已标记完成"}


@router.get("/case/{case_id}/records", response_model=List[ReviewRecordResponse])
def get_review_records(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    records = case.review_records
    result = []
    for record in records:
        record_dict = {
            "id": record.id,
            "case_id": record.case_id,
            "reviewer_id": record.reviewer_id,
            "reviewer_name": record.reviewer.name if record.reviewer else None,
            "action": record.action,
            "opinion": record.opinion,
            "result": record.result,
            "approved_amount": record.approved_amount,
            "created_at": record.created_at
        }
        result.append(record_dict)

    return result


@router.get("/pending", response_model=List[CaseResponse])
def get_pending_review_cases(
    reviewer_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ClaimCase).filter(
        ClaimCase.status.in_([ClaimStatus.PENDING_REVIEW, ClaimStatus.REVIEWING])
    )

    if reviewer_id:
        query = query.filter(ClaimCase.reviewer_id == reviewer_id)

    return query.order_by(ClaimCase.risk_score.desc(), ClaimCase.created_at.asc()).all()
