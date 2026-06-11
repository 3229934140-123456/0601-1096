from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os
import hashlib
from datetime import datetime

from database import get_db
from models import ClaimCase, Document, ClaimStatus, DocumentType
from schemas import CaseCreate, CaseResponse, CaseDetailResponse, CaseUpdate, DocumentResponse
from config import settings

router = APIRouter(prefix="/api/cases", tags=["案件提交"])


@router.post("", response_model=CaseResponse)
def create_case(case_data: CaseCreate, db: Session = Depends(get_db)):
    existing_case = db.query(ClaimCase).filter(ClaimCase.case_no == case_data.case_no).first()
    if existing_case:
        raise HTTPException(status_code=400, detail=f"案件号 {case_data.case_no} 已存在")

    case = ClaimCase(
        case_no=case_data.case_no,
        policy_no=case_data.policy_no,
        claimant_name=case_data.claimant_name,
        claimant_id_card=case_data.claimant_id_card,
        insured_name=case_data.insured_name,
        insured_id_card=case_data.insured_id_card,
        claim_amount=case_data.claim_amount,
        accident_date=case_data.accident_date,
        status=ClaimStatus.SUBMITTED
    )

    db.add(case)
    db.commit()
    db.refresh(case)

    return case


@router.post("/{case_id}/upload", response_model=List[DocumentResponse])
async def upload_documents(
    case_id: int,
    files: List[UploadFile] = File(...),
    document_types: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    type_list = document_types.split(",") if document_types else []

    uploaded_docs = []

    for i, file in enumerate(files):
        doc_type = DocumentType.OTHER
        if i < len(type_list):
            try:
                doc_type = DocumentType(type_list[i].strip())
            except:
                doc_type = DocumentType.OTHER

        file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = settings.UPLOAD_DIR / unique_filename

        content = await file.read()
        file_hash = hashlib.md5(content).hexdigest()

        with open(file_path, "wb") as f:
            f.write(content)

        existing_doc = db.query(Document).filter(
            Document.case_id == case_id,
            Document.file_hash == file_hash
        ).first()

        is_duplicate = existing_doc is not None
        duplicate_with = existing_doc.id if existing_doc else None

        doc = Document(
            case_id=case_id,
            document_type=doc_type,
            file_name=file.filename or unique_filename,
            file_path=str(file_path),
            file_size=len(content),
            file_hash=file_hash,
            is_duplicate=is_duplicate,
            duplicate_with=duplicate_with
        )

        db.add(doc)
        uploaded_docs.append(doc)

    db.commit()

    for doc in uploaded_docs:
        db.refresh(doc)

    return uploaded_docs


@router.get("", response_model=List[CaseResponse])
def list_cases(
    skip: int = 0,
    limit: int = 100,
    status: Optional[ClaimStatus] = None,
    is_high_risk: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ClaimCase)

    if status:
        query = query.filter(ClaimCase.status == status)
    if is_high_risk is not None:
        query = query.filter(ClaimCase.is_high_risk == is_high_risk)

    cases = query.order_by(ClaimCase.created_at.desc()).offset(skip).limit(limit).all()
    return cases


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return case


@router.put("/{case_id}", response_model=CaseResponse)
def update_case(case_id: int, update_data: CaseUpdate, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(case, key, value)

    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(case)

    return case


@router.get("/{case_id}/documents", response_model=List[DocumentResponse])
def get_case_documents(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.documents
