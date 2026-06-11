from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import asyncio
from datetime import datetime, timedelta

from database import get_db
from models import ClaimCase, RuleCheckResult, OCRResult, RiskAlert, ClaimStatus, RiskLevel, RuleManualStatus
from schemas import RiskAnalysisRequest, RiskAnalysisResponse, RiskAlertResponse, RuleStatsSummary
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
        effective_failed_count = 0
        confirmed_false_positive_count = 0
        for rule in rule_results:
            manual_status = rule.manual_status.value if rule.manual_status else "unconfirmed"
            is_effectively_failed = (not rule.passed) and manual_status not in ["false_positive"]
            if is_effectively_failed and rule.severity == "error":
                effective_failed_count += 1
            if manual_status == "false_positive":
                confirmed_false_positive_count += 1

            rule_data_list.append({
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "passed": rule.passed,
                "severity": rule.severity,
                "actual_value": rule.actual_value,
                "manual_status": manual_status,
                "effectively_failed": is_effectively_failed
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
                    "status": hc.status.value if hc.status else "unknown"
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

        if case.is_high_risk or effective_failed_count > 0:
            case.status = ClaimStatus.PENDING_REVIEW
        else:
            case.status = ClaimStatus.RISK_ANALYZED

        db.commit()

        for alert in saved_alerts:
            db.refresh(alert)

        rule_total = len(rule_results)
        rule_passed = sum(1 for r in rule_results if r.passed)
        rule_failed = rule_total - rule_passed
        false_positive_count = sum(1 for r in rule_results if r.manual_status and r.manual_status.value == "false_positive")
        confirmed_count = sum(1 for r in rule_results if r.manual_status and r.manual_status.value == "confirmed")
        need_supplement_count = sum(1 for r in rule_results if r.manual_status and r.manual_status.value == "need_supplement")
        unconfirmed_count = sum(1 for r in rule_results if not r.manual_status or r.manual_status.value == "unconfirmed")
        pass_rate = round(rule_passed / rule_total * 100, 2) if rule_total > 0 else 0

        has_critical = any(a.risk_level and a.risk_level.value == "critical" for a in saved_alerts)
        has_high = any(a.risk_level and a.risk_level.value == "high" for a in saved_alerts)
        manual_processed = false_positive_count > 0 or confirmed_count > 0 or need_supplement_count > 0

        if case.review_result and case.review_result.value == "approved":
            recommendation = "建议予以赔付"
            conclusion_text = "经AI初审及人工复核，该案审核通过。"
        elif case.review_result and case.review_result.value == "rejected":
            recommendation = "建议拒绝赔付"
            conclusion_text = "经AI初审及人工复核，该案审核拒绝。"
        elif case.review_result and case.review_result.value == "need_supplement":
            recommendation = "需要补充材料后再审"
            conclusion_text = "该案需要补充相关材料后重新审核。"
        else:
            if has_critical:
                recommendation = "建议人工重点复核"
                conclusion_text = "检测到严重风险项，建议由资深理赔人员进行人工复核。"
            elif has_high or effective_failed_count > 0 or pass_rate < 80:
                recommendation = "建议人工复核"
                conclusion_text = "存在较高风险或规则校验未通过，建议进行人工复核。"
            else:
                recommendation = "建议自动通过"
                conclusion_text = "AI初审未发现明显风险，规则校验通过率较高，建议自动通过。"

        manual_details = []
        if false_positive_count > 0:
            manual_details.append(f"已人工确认{false_positive_count}项误报规则")
        if need_supplement_count > 0:
            manual_details.append(f"{need_supplement_count}项规则已标记需补件")
        if confirmed_count > 0:
            manual_details.append(f"{confirmed_count}项规则已人工确认")
        if manual_details:
            conclusion_text += "（" + "，".join(manual_details) + "）"

        rule_stats = RuleStatsSummary(
            total=rule_total,
            passed=rule_passed,
            failed=rule_failed,
            effective_failed=effective_failed_count,
            false_positive_count=false_positive_count,
            confirmed_count=confirmed_count,
            need_supplement_count=need_supplement_count,
            unconfirmed_count=unconfirmed_count,
            pass_rate=pass_rate
        )

        return RiskAnalysisResponse(
            success=True,
            message="风险分析完成",
            risk_alerts=saved_alerts,
            overall_risk_level=case.risk_level,
            overall_risk_score=case.risk_score,
            is_high_risk=case.is_high_risk,
            rule_stats=rule_stats,
            recommendation=recommendation,
            conclusion=conclusion_text,
            manual_processed=manual_processed
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
