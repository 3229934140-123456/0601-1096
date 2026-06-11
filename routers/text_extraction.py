from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import asyncio

from database import get_db
from models import ClaimCase, OCRResult, ExtractedData, ClaimStatus
from schemas import ExtractionRequest, ExtractionResponse, ExtractedDataResponse
from mock_ai_service import MockNLPService

router = APIRouter(prefix="/api/extraction", tags=["文本抽取"])


@router.post("/extract", response_model=ExtractionResponse)
async def extract_data(request: ExtractionRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    case.status = ClaimStatus.EXTRACTION_PROCESSING
    db.commit()

    try:
        await asyncio.sleep(0.1)

        if request.ocr_result_id:
            ocr_results = db.query(OCRResult).filter(
                OCRResult.id == request.ocr_result_id,
                OCRResult.case_id == request.case_id
            ).all()
        else:
            ocr_results = db.query(OCRResult).filter(
                OCRResult.case_id == request.case_id
            ).all()

        if not ocr_results:
            return ExtractionResponse(
                success=False,
                message="未找到OCR识别结果，请先进行OCR识别",
                extracted_data=[]
            )

        all_extracted = []
        for ocr_result in ocr_results:
            document = ocr_result.document
            extracted_items = MockNLPService.extract(
                ocr_text=ocr_result.recognized_text or "",
                document_type=document.document_type.value if document else "unknown"
            )

            for item in extracted_items:
                extracted_data = ExtractedData(
                    case_id=request.case_id,
                    source_type=item["source_type"],
                    key=item["key"],
                    value=item["value"],
                    value_type=item["value_type"],
                    confidence=item["confidence"],
                    extracted_from=f"ocr_result_{ocr_result.id}:{item['extracted_from']}"
                )
                db.add(extracted_data)
                all_extracted.append(extracted_data)

        case.status = ClaimStatus.EXTRACTION_COMPLETED
        db.commit()

        for data in all_extracted:
            db.refresh(data)

        return ExtractionResponse(
            success=True,
            message=f"成功抽取{len(all_extracted)}条数据",
            extracted_data=all_extracted
        )

    except Exception as e:
        db.rollback()
        case.status = ClaimStatus.OCR_COMPLETED
        db.commit()
        raise HTTPException(status_code=500, detail=f"文本抽取失败: {str(e)}")


@router.get("/case/{case_id}/results", response_model=List[ExtractedDataResponse])
def get_extraction_results(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.extracted_data
