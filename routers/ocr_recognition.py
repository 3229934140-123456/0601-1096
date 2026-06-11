from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio

from database import get_db
from models import ClaimCase, Document, OCRResult, ClaimStatus
from schemas import OCRRequest, OCRResponse, OCRResultResponse
from mock_ai_service import MockOCRService

router = APIRouter(prefix="/api/ocr", tags=["图片识别"])


@router.post("/recognize", response_model=OCRResponse)
async def recognize_document(request: OCRRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    document = db.query(Document).filter(
        Document.id == request.document_id,
        Document.case_id == request.case_id
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    case.status = ClaimStatus.OCR_PROCESSING
    db.commit()

    try:
        await asyncio.sleep(0.1)

        ocr_data = MockOCRService.recognize(
            document_type=document.document_type.value,
            file_path=document.file_path,
            file_name=document.file_name
        )

        ocr_result = OCRResult(
            case_id=request.case_id,
            document_id=request.document_id,
            recognized_text=ocr_data["recognized_text"],
            confidence=ocr_data["confidence"],
            recognized_amount=ocr_data["recognized_amount"],
            recognized_date=ocr_data["recognized_date"],
            recognized_name=ocr_data["recognized_name"],
            recognized_id_card=ocr_data["recognized_id_card"],
            invoice_no=ocr_data["invoice_no"],
            hospital_name=ocr_data["hospital_name"],
            diagnosis=ocr_data["diagnosis"],
            processing_time_ms=ocr_data["processing_time_ms"],
            extra_data=ocr_data["extra_data"]
        )

        db.add(ocr_result)
        document.ocr_completed = True

        case.status = ClaimStatus.OCR_COMPLETED
        db.commit()
        db.refresh(ocr_result)

        return OCRResponse(
            success=True,
            message="OCR识别完成",
            ocr_result=ocr_result
        )

    except Exception as e:
        db.rollback()
        case.status = ClaimStatus.SUBMITTED
        db.commit()
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")


@router.post("/case/{case_id}/recognize-all", response_model=List[OCRResultResponse])
async def recognize_all_documents(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    documents = db.query(Document).filter(
        Document.case_id == case_id,
        Document.ocr_completed == False
    ).all()

    if not documents:
        all_results = db.query(OCRResult).filter(OCRResult.case_id == case_id).all()
        return all_results

    case.status = ClaimStatus.OCR_PROCESSING
    db.commit()

    ocr_results = []
    try:
        for doc in documents:
            await asyncio.sleep(0.1)

            ocr_data = MockOCRService.recognize(
                document_type=doc.document_type.value,
                file_path=doc.file_path,
                file_name=doc.file_name
            )

            ocr_result = OCRResult(
                case_id=case_id,
                document_id=doc.id,
                recognized_text=ocr_data["recognized_text"],
                confidence=ocr_data["confidence"],
                recognized_amount=ocr_data["recognized_amount"],
                recognized_date=ocr_data["recognized_date"],
                recognized_name=ocr_data["recognized_name"],
                recognized_id_card=ocr_data["recognized_id_card"],
                invoice_no=ocr_data["invoice_no"],
                hospital_name=ocr_data["hospital_name"],
                diagnosis=ocr_data["diagnosis"],
                processing_time_ms=ocr_data["processing_time_ms"],
                extra_data=ocr_data["extra_data"]
            )

            db.add(ocr_result)
            doc.ocr_completed = True
            ocr_results.append(ocr_result)

        case.status = ClaimStatus.OCR_COMPLETED
        db.commit()

        for result in ocr_results:
            db.refresh(result)

        return ocr_results

    except Exception as e:
        case.status = ClaimStatus.SUBMITTED
        db.commit()
        raise HTTPException(status_code=500, detail=f"批量OCR识别失败: {str(e)}")


@router.get("/case/{case_id}/results", response_model=List[OCRResultResponse])
def get_ocr_results(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.ocr_results
