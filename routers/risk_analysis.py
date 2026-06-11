from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import asyncio
from datetime import datetime, timedelta

from database import get_db
from models import ClaimCase, RuleCheckResult, OCRResult, RiskAlert, ClaimStatus, RiskLevel
from schemas import RiskAnalysisRequest, RiskAnalysisResponse, RiskAlertResponse
from mock_ai_service import MockRiskAnalyzer

router = APIRouter(prefix="/api/risk", tags=["风险提示"])


@router.post("/analyze", response_model=RiskAnalysisResponse)
async def analyze_risk(request: RiskAnalysisRequest, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    case.status = ClaimStatus.RISK_ANALYZING
    db.commit()

    try:
        await asyncio.sleep(0.1)

        rule_results = db.query(RuleCheckResult).filter(RuleCheckResult.case_id == request.case_id).all()
        ocr_results = db.query(OCRResult).filter(OCRResult.case_id == request.case_id).all()

        case_data = {
            "case_no": case.case_no,
            "policy_no": case.policy_no,
            "claimant_name": case.claimant_name,
            "claimant_id_card": case.claimant_id_card,
            "insured_name": case.insured_name,
            "insured_id_card": case.insured_id_card,
            "claim_amount": case.claim_amount,
            "accident_date": case.accident_date,
            "claim_date": case.claim_date
        }

        rule_data_list = []
        for rule in rule_results:
            rule_data_list.append({
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "passed": rule.passed,
                "severity": rule.severity,
                "actual_value": rule.actual_value
            })

        ocr_data_list = []
        for ocr in ocr_results:
            doc = ocr.document
            ocr_data_list.append({
                "document_type": doc.document_type.value if doc else "unknown",
                "recognized_text": ocr.recognized_text,
                "recognized_amount": ocr.recognized_amount,
                "recognized_date": ocr.recognized_date,
                "diagnosis": ocr.diagnosis
            })

        id_card = case.claimant_id_card or case.insured_id_card
        historical_cases = []
        if id_card:
            cutoff_date = datetime.utcnow() - timedelta(days=365)
            history = db.query(ClaimCase).filter(
                ClaimCase.id != case.id,
                (ClaimCase.claimant_id_card == id_card) | (ClaimCase.insured_id_card == id_card),
                ClaimCase.claim_date >= cutoff_date
            ).all()

            for hc in history:
                historical_cases.append({
                    "case_no": hc.case_no,
                    "claim_amount": hc.claim_amount,
                    "claim_date": hc.claim_date,
                    "status": hc.status.value
                })

        risk_result = MockRiskAnalyzer.analyze(case_data, rule_data_list, ocr_data_list, historical_cases)

        db.query(RiskAlert).filter(RiskAlert.case_id == request.case_id).delete()

        saved_alerts = []
        for alert in risk_result["risk_alerts"]:
            risk_alert = RiskAlert(
                case_id=request.case_id,
                alert_code=alert["alert_code"],
                alert_type=alert["alert_type"],
                title=alert["title"],
                description=alert["description"],
                risk_level=RiskLevel(alert["risk_level"]),
                risk_score_contribution=alert["risk_score_contribution"],
                evidence=alert["evidence"],
                explanation=alert["explanation"],
                recommendation=alert["recommendation"]
            )
            db.add(risk_alert)
            saved_alerts.append(risk_alert)

        case.risk_level = RiskLevel(risk_result["overall_risk_level"])
        case.risk_score = risk_result["overall_risk_score"]
        case.is_high_risk = risk_result["is_high_risk"]
        case.status = ClaimStatus.RISK_ANALYZED

        if case.is_high_risk:
            case.status = ClaimStatus.PENDING_REVIEW

        db.commit()

        for alert in saved_alerts:
            db.refresh(alert)

        return RiskAnalysisResponse(
            success=True,
            message="风险分析完成",
            risk_alerts=saved_alerts,
            overall_risk_level=case.risk_level,
            overall_risk_score=case.risk_score,
            is_high_risk=case.is_high_risk
        )

    except Exception as e:
        db.rollback()
        case.status = ClaimStatus.RULE_CHECKED
        db.commit()
        raise HTTPException(status_code=500, detail=f"风险分析失败: {str(e)}")


@router.get("/case/{case_id}/alerts", response_model=List[RiskAlertResponse])
def get_risk_alerts(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    return case.risk_alerts


@router.get("/high-risk", response_model=List[RiskAlertResponse])
def get_high_risk_cases(
    skip: int = 0,
    limit: int = 100,
    min_risk_score: float = 50.0,
    db: Session = Depends(get_db)
):
    alerts = db.query(RiskAlert).join(ClaimCase).filter(
        ClaimCase.risk_score >= min_risk_score
    ).order_by(ClaimCase.risk_score.desc()).offset(skip).limit(limit).all()

    return alerts
