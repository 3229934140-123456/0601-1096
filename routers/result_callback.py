from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json
import uuid
import os
import httpx

from database import get_db
from models import ClaimCase, ClaimStatus, ReviewResult, CallLog
from schemas import ExportRequest, ExportResponse, ResultCallbackRequest
from config import settings

router = APIRouter(prefix="/api/result", tags=["结果回传"])


@router.post("/export", response_model=ExportResponse)
async def export_review_summary(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    summary = generate_review_summary(case, db)

    if request.format == "pdf":
        file_name = f"review_summary_{case.case_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        file_path = settings.EXPORT_DIR / file_name
        background_tasks.add_task(generate_pdf_report, file_path, summary)
    elif request.format == "excel":
        file_name = f"review_summary_{case.case_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        file_path = settings.EXPORT_DIR / file_name
        background_tasks.add_task(generate_excel_report, file_path, summary)
    else:
        file_name = f"review_summary_{case.case_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        file_path = settings.EXPORT_DIR / file_name
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    return ExportResponse(
        success=True,
        message="审查摘要生成中，将在后台完成",
        file_url=f"/api/result/download/{file_name}",
        file_name=file_name,
        summary=summary
    )


@router.get("/download/{file_name}")
async def download_export(file_name: str):
    file_path = settings.EXPORT_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type="application/octet-stream"
    )


@router.get("/{case_id}/summary")
def get_review_summary(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    summary = generate_review_summary(case, db)
    return summary


@router.post("/callback")
async def send_result_callback(
    request: ResultCallbackRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    case = db.query(ClaimCase).filter(ClaimCase.id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    summary = generate_review_summary(case, db)
    callback_data = {
        "case_id": case.id,
        "case_no": case.case_no,
        "status": case.status.value,
        "result": case.review_result.value if case.review_result else None,
        "summary": summary,
        "custom_data": request.callback_data
    }

    background_tasks.add_task(send_callback, request.callback_url, callback_data)

    return {
        "success": True,
        "message": "结果回传任务已提交，将在后台执行",
        "callback_url": request.callback_url,
        "data": callback_data
    }


@router.post("/{case_id}/complete")
def complete_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(ClaimCase).filter(ClaimCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    if case.status not in [ClaimStatus.APPROVED, ClaimStatus.REJECTED]:
        raise HTTPException(status_code=400, detail="案件尚未完成审核")

    case.status = ClaimStatus.COMPLETED
    db.commit()
    db.refresh(case)

    return {
        "success": True,
        "message": "案件已标记完成",
        "case_no": case.case_no,
        "final_status": case.status.value,
        "final_result": case.review_result.value if case.review_result else None,
        "approved_amount": case.final_approved_amount
    }


def generate_review_summary(case: ClaimCase, db: Session) -> Dict[str, Any]:
    ocr_results = case.ocr_results
    extracted_data = case.extracted_data
    rule_checks = case.rule_checks
    risk_alerts = case.risk_alerts
    review_records = case.review_records
    supplement_items = case.supplement_items
    documents = case.documents

    total_invoice_amount = sum(
        ocr.recognized_amount for ocr in ocr_results
        if ocr.recognized_amount and ocr.document and ocr.document.document_type.value == "invoice"
    )

    rule_passed = sum(1 for r in rule_checks if r.passed)
    rule_total = len(rule_checks)

    critical_alerts = [a for a in risk_alerts if a.risk_level.value == "critical"]
    high_alerts = [a for a in risk_alerts if a.risk_level.value == "high"]
    medium_alerts = [a for a in risk_alerts if a.risk_level.value == "medium"]

    summary = {
        "basic_info": {
            "case_no": case.case_no,
            "policy_no": case.policy_no,
            "claimant_name": case.claimant_name,
            "claimant_id_card": case.claimant_id_card,
            "insured_name": case.insured_name,
            "insured_id_card": case.insured_id_card,
            "claim_amount": case.claim_amount,
            "accident_date": case.accident_date,
            "claim_date": case.claim_date,
            "created_at": case.created_at,
            "updated_at": case.updated_at
        },
        "processing_overview": {
            "current_status": case.status.value,
            "current_status_desc": get_status_description(case.status),
            "risk_level": case.risk_level.value,
            "risk_score": case.risk_score,
            "is_high_risk": case.is_high_risk,
            "total_documents": len(documents),
            "total_ocr_results": len(ocr_results),
            "total_invoice_amount": total_invoice_amount
        },
        "documents": [
            {
                "id": doc.id,
                "type": doc.document_type.value,
                "file_name": doc.file_name,
                "file_size": doc.file_size,
                "upload_time": doc.upload_time,
                "is_duplicate": doc.is_duplicate,
                "ocr_completed": doc.ocr_completed
            }
            for doc in documents
        ],
        "ocr_recognition": [
            {
                "id": ocr.id,
                "document_id": ocr.document_id,
                "document_type": ocr.document.document_type.value if ocr.document else None,
                "confidence": ocr.confidence,
                "recognized_amount": ocr.recognized_amount,
                "recognized_date": ocr.recognized_date,
                "recognized_name": ocr.recognized_name,
                "hospital_name": ocr.hospital_name,
                "diagnosis": ocr.diagnosis,
                "processing_time_ms": ocr.processing_time_ms
            }
            for ocr in ocr_results
        ],
        "extracted_data": [
            {
                "id": ed.id,
                "key": ed.key,
                "value": ed.value,
                "value_type": ed.value_type,
                "confidence": ed.confidence,
                "source_type": ed.source_type
            }
            for ed in extracted_data
        ],
        "rule_checks": {
            "summary": {
                "total": rule_total,
                "passed": rule_passed,
                "failed": rule_total - rule_passed,
                "pass_rate": round(rule_passed / rule_total * 100, 2) if rule_total > 0 else 0
            },
            "details": [
                {
                    "id": rc.id,
                    "rule_code": rc.rule_code,
                    "rule_name": rc.rule_name,
                    "passed": rc.passed,
                    "severity": rc.severity,
                    "actual_value": rc.actual_value,
                    "expected_value": rc.expected_value,
                    "description": rc.description,
                    "suggestion": rc.suggestion
                }
                for rc in rule_checks
            ]
        },
        "risk_analysis": {
            "summary": {
                "overall_risk_level": case.risk_level.value,
                "overall_risk_score": case.risk_score,
                "is_high_risk": case.is_high_risk,
                "critical_alerts": len(critical_alerts),
                "high_alerts": len(high_alerts),
                "medium_alerts": len(medium_alerts)
            },
            "alerts": [
                {
                    "id": alert.id,
                    "alert_code": alert.alert_code,
                    "alert_type": alert.alert_type,
                    "title": alert.title,
                    "description": alert.description,
                    "risk_level": alert.risk_level.value,
                    "risk_score_contribution": alert.risk_score_contribution,
                    "explanation": alert.explanation,
                    "recommendation": alert.recommendation,
                    "evidence": alert.evidence
                }
                for alert in risk_alerts
            ]
        },
        "manual_review": {
            "reviewer": case.reviewer.name if case.reviewer else None,
            "reviewer_id": case.reviewer_id,
            "review_result": case.review_result.value if case.review_result else None,
            "review_opinion": case.review_opinion,
            "review_date": case.review_date,
            "final_approved_amount": case.final_approved_amount,
            "records": [
                {
                    "id": rr.id,
                    "action": rr.action,
                    "opinion": rr.opinion,
                    "result": rr.result.value if rr.result else None,
                    "approved_amount": rr.approved_amount,
                    "reviewer_name": rr.reviewer.name if rr.reviewer else None,
                    "created_at": rr.created_at
                }
                for rr in review_records
            ]
        },
        "supplements": {
            "total": len(supplement_items),
            "completed": sum(1 for s in supplement_items if s.is_completed),
            "pending": sum(1 for s in supplement_items if not s.is_completed),
            "items": [
                {
                    "id": si.id,
                    "item_code": si.item_code,
                    "item_name": si.item_name,
                    "description": si.description,
                    "reason": si.reason,
                    "priority": si.priority,
                    "is_completed": si.is_completed,
                    "completed_at": si.completed_at
                }
                for si in supplement_items
            ]
        },
        "conclusion": generate_conclusion(case, rule_passed, rule_total, risk_alerts)
    }

    return summary


def get_status_description(status: ClaimStatus) -> str:
    descriptions = {
        ClaimStatus.SUBMITTED: "案件已提交",
        ClaimStatus.OCR_PROCESSING: "OCR识别中",
        ClaimStatus.OCR_COMPLETED: "OCR识别完成",
        ClaimStatus.EXTRACTION_PROCESSING: "信息抽取中",
        ClaimStatus.EXTRACTION_COMPLETED: "信息抽取完成",
        ClaimStatus.RULE_CHECKING: "规则核对中",
        ClaimStatus.RULE_CHECKED: "规则核对完成",
        ClaimStatus.RISK_ANALYZING: "风险分析中",
        ClaimStatus.RISK_ANALYZED: "风险分析完成",
        ClaimStatus.PENDING_REVIEW: "待人工复核",
        ClaimStatus.REVIEWING: "人工复核中",
        ClaimStatus.REVIEWED: "复核完成",
        ClaimStatus.SUPPLEMENT_REQUESTED: "待补充材料",
        ClaimStatus.APPROVED: "审核通过",
        ClaimStatus.REJECTED: "审核拒绝",
        ClaimStatus.WITHDRAWN: "已撤回",
        ClaimStatus.COMPLETED: "案件完成"
    }
    return descriptions.get(status, status.value)


def generate_conclusion(case: ClaimCase, rule_passed: int, rule_total: int, risk_alerts) -> Dict[str, Any]:
    has_critical = any(a.risk_level.value == "critical" for a in risk_alerts)
    has_high = any(a.risk_level.value == "high" for a in risk_alerts)
    rule_pass_rate = rule_passed / rule_total * 100 if rule_total > 0 else 100

    if case.review_result == ReviewResult.APPROVED:
        recommendation = "建议予以赔付"
        conclusion_text = f"经AI初审及人工复核，该案审核通过。"
    elif case.review_result == ReviewResult.REJECTED:
        recommendation = "建议拒绝赔付"
        conclusion_text = f"经AI初审及人工复核，该案审核拒绝。"
    elif case.review_result == ReviewResult.NEED_SUPPLEMENT:
        recommendation = "需要补充材料后再审"
        conclusion_text = f"该案需要补充相关材料后重新审核。"
    else:
        if has_critical:
            recommendation = "建议人工重点复核"
            conclusion_text = "检测到严重风险项，建议由资深理赔人员进行人工复核。"
        elif has_high or rule_pass_rate < 80:
            recommendation = "建议人工复核"
            conclusion_text = "存在较高风险或规则通过率较低，建议进行人工复核。"
        else:
            recommendation = "建议自动通过"
            conclusion_text = "AI初审未发现明显风险，规则校验通过率较高，建议自动通过。"

    if has_critical or has_high:
        risk_assessment = f"存在{len([a for a in risk_alerts if a.risk_level.value in ['critical', 'high']])}项高风险预警"
    else:
        risk_assessment = "未发现明显风险"

    return {
        "conclusion": conclusion_text,
        "risk_assessment": risk_assessment,
        "rule_pass_rate": round(rule_pass_rate, 2),
        "recommendation": recommendation,
        "approved_amount": case.final_approved_amount,
        "claim_amount": case.claim_amount,
        "amount_difference": (case.claim_amount - case.final_approved_amount) if case.final_approved_amount else None
    }


def generate_pdf_report(file_path, summary):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        doc = SimpleDocTemplate(str(file_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        try:
            pdfmetrics.registerFont(TTFont('SimSun', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
            font_name = 'SimSun'
        except:
            font_name = 'Helvetica'

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=20,
            spaceAfter=30,
            alignment=1
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=font_name,
            fontSize=14,
            spaceAfter=12,
            textColor=colors.darkblue
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=10,
            spaceAfter=6
        )

        story.append(Paragraph("保险理赔材料初审报告", title_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("一、基本信息", heading_style))
        basic_info = summary["basic_info"]
        basic_data = [
            ["案件号", basic_info["case_no"]],
            ["保单号", basic_info["policy_no"] or "-"],
            ["索赔人", basic_info["claimant_name"] or "-"],
            ["被保险人", basic_info["insured_name"] or "-"],
            ["索赔金额", f"{basic_info['claim_amount']} 元"],
            ["事故日期", str(basic_info["accident_date"]) if basic_info["accident_date"] else "-"]
        ]
        basic_table = Table(basic_data, colWidths=[1.5 * inch, 3.5 * inch])
        basic_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), font_name, 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 12))

        story.append(Paragraph("二、处理概览", heading_style))
        overview = summary["processing_overview"]
        story.append(Paragraph(f"当前状态: {overview['current_status_desc']}", normal_style))
        story.append(Paragraph(f"风险等级: {overview['risk_level']} (风险得分: {overview['risk_score']})", normal_style))
        story.append(Paragraph(f"高风险标记: {'是' if overview['is_high_risk'] else '否'}", normal_style))
        story.append(Paragraph(f"上传文件数: {overview['total_documents']} 份", normal_style))
        story.append(Paragraph(f"发票总金额: {overview['total_invoice_amount']} 元", normal_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("三、规则校验", heading_style))
        rule_summary = summary["rule_checks"]["summary"]
        story.append(Paragraph(f"规则总数: {rule_summary['total']}, 通过: {rule_summary['passed']}, "
                               f"通过率: {rule_summary['pass_rate']}%", normal_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("四、风险预警", heading_style))
        risk_summary = summary["risk_analysis"]["summary"]
        story.append(Paragraph(f"严重风险: {risk_summary['critical_alerts']} 项, "
                               f"高风险: {risk_summary['high_alerts']} 项, "
                               f"中风险: {risk_summary['medium_alerts']} 项", normal_style))
        for alert in summary["risk_analysis"]["alerts"]:
            story.append(Paragraph(f"- [{alert['risk_level'].upper()}] {alert['title']}: {alert['description']}", normal_style))
            if alert["recommendation"]:
                story.append(Paragraph(f"  建议: {alert['recommendation']}", normal_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("五、审核结论", heading_style))
        conclusion = summary["conclusion"]
        story.append(Paragraph(f"结论: {conclusion['conclusion']}", normal_style))
        story.append(Paragraph(f"风险评估: {conclusion['risk_assessment']}", normal_style))
        story.append(Paragraph(f"建议: {conclusion['recommendation']}", normal_style))
        if conclusion["approved_amount"] is not None:
            story.append(Paragraph(f"核定赔付金额: {conclusion['approved_amount']} 元", normal_style))

        story.append(Spacer(1, 24))
        story.append(Paragraph(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))

        doc.build(story)
    except Exception as e:
        print(f"PDF生成失败: {e}")
        with open(str(file_path).replace('.pdf', '.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)


def generate_excel_report(file_path, summary):
    try:
        import pandas as pd

        with pd.ExcelWriter(str(file_path), engine='openpyxl') as writer:
            basic_info = summary["basic_info"]
            df_basic = pd.DataFrame([
                ["案件号", basic_info["case_no"]],
                ["保单号", basic_info["policy_no"] or "-"],
                ["索赔人", basic_info["claimant_name"] or "-"],
                ["被保险人", basic_info["insured_name"] or "-"],
                ["身份证号", basic_info["claimant_id_card"] or "-"],
                ["索赔金额", f"{basic_info['claim_amount']} 元"],
                ["事故日期", str(basic_info["accident_date"]) if basic_info["accident_date"] else "-"],
                ["提交日期", str(basic_info["created_at"])]
            ], columns=["项目", "内容"])
            df_basic.to_excel(writer, sheet_name="基本信息", index=False)

            overview = summary["processing_overview"]
            df_overview = pd.DataFrame([
                ["当前状态", overview["current_status_desc"]],
                ["风险等级", overview["risk_level"]],
                ["风险得分", overview["risk_score"]],
                ["高风险标记", "是" if overview["is_high_risk"] else "否"],
                ["上传文件数", f"{overview['total_documents']} 份"],
                ["发票总金额", f"{overview['total_invoice_amount']} 元"]
            ], columns=["项目", "内容"])
            df_overview.to_excel(writer, sheet_name="处理概览", index=False)

            rule_details = summary["rule_checks"]["details"]
            if rule_details:
                df_rules = pd.DataFrame(rule_details)
                df_rules = df_rules[["rule_code", "rule_name", "passed", "severity", "description"]]
                df_rules.columns = ["规则编码", "规则名称", "是否通过", "严重程度", "说明"]
                df_rules.to_excel(writer, sheet_name="规则校验", index=False)

            alert_details = summary["risk_analysis"]["alerts"]
            if alert_details:
                df_alerts = pd.DataFrame(alert_details)
                df_alerts = df_alerts[["alert_code", "title", "risk_level", "description", "recommendation"]]
                df_alerts.columns = ["预警编码", "预警标题", "风险等级", "描述", "建议"]
                df_alerts.to_excel(writer, sheet_name="风险预警", index=False)

            conclusion = summary["conclusion"]
            df_conclusion = pd.DataFrame([
                ["审核结论", conclusion["conclusion"]],
                ["风险评估", conclusion["risk_assessment"]],
                ["规则通过率", f"{conclusion['rule_pass_rate']}%"],
                ["处理建议", conclusion["recommendation"]],
                ["核定赔付金额", f"{conclusion['approved_amount']} 元" if conclusion["approved_amount"] else "-"],
                ["索赔金额", f"{conclusion['claim_amount']} 元"]
            ], columns=["项目", "内容"])
            df_conclusion.to_excel(writer, sheet_name="审核结论", index=False)

    except Exception as e:
        print(f"Excel生成失败: {e}")
        with open(str(file_path).replace('.xlsx', '.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)


async def send_callback(url: str, data: Dict[str, Any]):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            print(f"回调成功: {url}")
            return response.json()
    except Exception as e:
        print(f"回调失败: {url}, 错误: {e}")
        return None
