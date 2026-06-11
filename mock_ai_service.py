import random
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import re


class MockOCRService:
    @staticmethod
    def recognize(document_type: str, file_path: str, file_name: str) -> Dict[str, Any]:
        confidence = round(random.uniform(0.85, 0.99), 4)
        processing_time = random.randint(200, 1500)

        result = {
            "recognized_text": "",
            "confidence": confidence,
            "recognized_amount": None,
            "recognized_date": None,
            "recognized_name": None,
            "recognized_id_card": None,
            "invoice_no": None,
            "hospital_name": None,
            "diagnosis": None,
            "processing_time_ms": processing_time,
            "extra_data": {}
        }

        if document_type == "policy":
            names = ["张三", "李四", "王五", "赵六", "陈七"]
            name = random.choice(names)
            policy_no = f"POL{random.randint(100000, 999999)}"
            amount = round(random.uniform(5000, 200000), 2)
            start_date = datetime.now() - timedelta(days=random.randint(30, 365))

            result["recognized_text"] = f"""
            保险单
            保单号: {policy_no}
            投保人: {name}
            身份证号: 110101{random.randint(1980, 2000):04d}{random.randint(1, 12):02d}{random.randint(1, 28):02d}{random.randint(1000, 9999):04d}
            保险金额: {amount}元
            保险期间: {start_date.strftime('%Y-%m-%d')} 至 {(start_date + timedelta(days=365)).strftime('%Y-%m-%d')}
            """
            result["recognized_name"] = name
            result["recognized_id_card"] = re.search(r'\d{17}[\dXx]', result["recognized_text"]).group()
            result["recognized_amount"] = amount
            result["recognized_date"] = start_date
            result["extra_data"]["policy_no"] = policy_no

        elif document_type == "invoice":
            names = ["张三", "李四", "王五", "赵六", "陈七"]
            name = random.choice(names)
            hospitals = ["北京协和医院", "上海瑞金医院", "广州中山医院", "武汉同济医院", "成都华西医院"]
            hospital = random.choice(hospitals)
            amount = round(random.uniform(500, 50000), 2)
            invoice_date = datetime.now() - timedelta(days=random.randint(1, 30))
            invoice_no = f"INV{random.randint(100000, 999999)}"
            diagnoses = ["急性阑尾炎", "高血压", "糖尿病", "骨折", "肺炎", "心脏病"]
            diagnosis = random.choice(diagnoses)

            result["recognized_text"] = f"""
            医疗收费票据
            发票号码: {invoice_no}
            日期: {invoice_date.strftime('%Y-%m-%d')}
            患者姓名: {name}
            就诊医院: {hospital}
            诊断: {diagnosis}
            金额: {amount}元
            收费项目: 检查费 药品费 治疗费
            """
            result["recognized_name"] = name
            result["recognized_amount"] = amount
            result["recognized_date"] = invoice_date
            result["invoice_no"] = invoice_no
            result["hospital_name"] = hospital
            result["diagnosis"] = diagnosis
            result["extra_data"]["diagnosis"] = diagnosis

        elif document_type == "id_card":
            names = ["张三", "李四", "王五", "赵六", "陈七"]
            name = random.choice(names)
            id_card = f"110101{random.randint(1980, 2000):04d}{random.randint(1, 12):02d}{random.randint(1, 28):02d}{random.randint(1000, 9999):04d}"

            result["recognized_text"] = f"""
            中华人民共和国居民身份证
            姓名: {name}
            性别: 男
            民族: 汉
            出生: {id_card[6:10]}年{int(id_card[10:12])}月{int(id_card[12:14])}日
            住址: 北京市朝阳区某某街道
            公民身份号码: {id_card}
            """
            result["recognized_name"] = name
            result["recognized_id_card"] = id_card
            result["recognized_date"] = datetime.strptime(id_card[6:14], "%Y%m%d")

        elif document_type == "receipt":
            amount = round(random.uniform(100, 10000), 2)
            receipt_date = datetime.now() - timedelta(days=random.randint(1, 15))
            receipt_no = f"RCT{random.randint(100000, 999999)}"

            result["recognized_text"] = f"""
            收款收据
            收据号: {receipt_no}
            日期: {receipt_date.strftime('%Y-%m-%d')}
            金额: {amount}元
            收款项目: 医药费
            """
            result["recognized_amount"] = amount
            result["recognized_date"] = receipt_date
            result["extra_data"]["receipt_no"] = receipt_no

        else:
            result["recognized_text"] = f"已识别{document_type}文档内容"
            result["recognized_amount"] = round(random.uniform(100, 10000), 2)
            result["recognized_date"] = datetime.now() - timedelta(days=random.randint(1, 30))

        return result


class MockNLPService:
    @staticmethod
    def extract(ocr_text: str, document_type: str) -> List[Dict[str, Any]]:
        extracted_items = []

        amount_match = re.search(r'金额[:：]\s*([\d.]+)', ocr_text)
        if amount_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "claim_amount",
                "value": amount_match.group(1),
                "value_type": "float",
                "confidence": round(random.uniform(0.9, 0.99), 4),
                "extracted_from": "text_matching"
            })

        name_match = re.search(r'(?:姓名|投保人|患者)[:：]\s*(\w+)', ocr_text)
        if name_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "person_name",
                "value": name_match.group(1),
                "value_type": "string",
                "confidence": round(random.uniform(0.85, 0.98), 4),
                "extracted_from": "text_matching"
            })

        id_match = re.search(r'(?:身份证号|公民身份号码)[:：]\s*(\d{17}[\dXx])', ocr_text)
        if id_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "id_card",
                "value": id_match.group(1),
                "value_type": "string",
                "confidence": round(random.uniform(0.92, 0.99), 4),
                "extracted_from": "text_matching"
            })

        date_match = re.search(r'(?:日期|出生)[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', ocr_text)
        if date_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "document_date",
                "value": date_match.group(1),
                "value_type": "date",
                "confidence": round(random.uniform(0.88, 0.97), 4),
                "extracted_from": "text_matching"
            })

        invoice_match = re.search(r'(?:发票号码|收据号|保单号)[:：]\s*(\w+)', ocr_text)
        if invoice_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "document_no",
                "value": invoice_match.group(1),
                "value_type": "string",
                "confidence": round(random.uniform(0.9, 0.98), 4),
                "extracted_from": "text_matching"
            })

        diagnosis_match = re.search(r'诊断[:：]\s*(\w+)', ocr_text)
        if diagnosis_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "diagnosis",
                "value": diagnosis_match.group(1),
                "value_type": "string",
                "confidence": round(random.uniform(0.85, 0.95), 4),
                "extracted_from": "text_matching"
            })

        hospital_match = re.search(r'(?:就诊医院|医院名称)[:：]\s*([^\\n]+)', ocr_text)
        if hospital_match:
            extracted_items.append({
                "source_type": document_type,
                "key": "hospital_name",
                "value": hospital_match.group(1).strip(),
                "value_type": "string",
                "confidence": round(random.uniform(0.88, 0.96), 4),
                "extracted_from": "text_matching"
            })

        return extracted_items


class MockRuleEngine:
    @staticmethod
    def check_rules(case_data: Dict[str, Any], extracted_data: List[Dict[str, Any]],
                    ocr_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rule_results = []

        rule_results.append({
            "rule_code": "RULE_001",
            "rule_name": "姓名一致性检查",
            "passed": case_data.get("claimant_name") == case_data.get("insured_name") or not case_data.get("insured_name"),
            "actual_value": f"索赔人: {case_data.get('claimant_name')}, 被保险人: {case_data.get('insured_name')}",
            "expected_value": "姓名一致",
            "description": "验证索赔人与被保险人姓名是否一致",
            "severity": "error" if case_data.get("claimant_name") and case_data.get("insured_name") and case_data.get("claimant_name") != case_data.get("insured_name") else "info"
        })

        id_card = case_data.get("claimant_id_card", "")
        id_valid = bool(len(id_card) in [15, 18] and re.match(r'^\d{15}$|^\d{17}[\dXx]$', id_card)) if id_card else True
        rule_results.append({
            "rule_code": "RULE_002",
            "rule_name": "身份证号格式校验",
            "passed": id_valid,
            "actual_value": id_card or "未提供",
            "expected_value": "15或18位有效身份证号",
            "description": "验证身份证号格式是否正确",
            "severity": "error" if not id_valid else "info"
        })

        claim_amount = case_data.get("claim_amount", 0)
        total_ocr_amount = sum(r.get("recognized_amount", 0) or 0 for r in ocr_results)
        amount_match = abs(claim_amount - total_ocr_amount) <= max(claim_amount, total_ocr_amount) * 0.1 if total_ocr_amount > 0 else True
        rule_results.append({
            "rule_code": "RULE_003",
            "rule_name": "索赔金额与票据金额比对",
            "passed": amount_match,
            "actual_value": f"索赔金额: {claim_amount}, 票据总额: {total_ocr_amount}",
            "expected_value": "差额不超过10%",
            "description": "核对索赔金额与票据总金额是否匹配",
            "severity": "warning" if not amount_match else "info"
        })

        policy_no = case_data.get("policy_no", "")
        policy_in_extracted = any(d.get("key") == "document_no" and "POL" in str(d.get("value", "")) for d in extracted_data)
        rule_results.append({
            "rule_code": "RULE_004",
            "rule_name": "保单号验证",
            "passed": bool(policy_no) or policy_in_extracted,
            "actual_value": f"提交保单号: {policy_no}",
            "expected_value": "保单号已提供",
            "description": "验证保单号是否已提供",
            "severity": "warning" if not policy_no and not policy_in_extracted else "info"
        })

        has_invoice = any(r.get("document_type") == "invoice" for r in ocr_results)
        rule_results.append({
            "rule_code": "RULE_005",
            "rule_name": "必要材料检查-发票",
            "passed": has_invoice,
            "actual_value": "已上传发票" if has_invoice else "未上传发票",
            "expected_value": "必须提供医疗发票",
            "description": "检查是否已上传必要的医疗发票",
            "severity": "error" if not has_invoice else "info"
        })

        has_id = any(r.get("document_type") == "id_card" for r in ocr_results)
        rule_results.append({
            "rule_code": "RULE_006",
            "rule_name": "必要材料检查-身份证明",
            "passed": has_id,
            "actual_value": "已上传身份证" if has_id else "未上传身份证",
            "expected_value": "必须提供身份证明",
            "description": "检查是否已上传必要的身份证明",
            "severity": "error" if not has_id else "info"
        })

        accident_date = case_data.get("accident_date")
        if accident_date:
            all_dates_valid = True
            for r in ocr_results:
                doc_date = r.get("recognized_date")
                if doc_date and doc_date < accident_date:
                    all_dates_valid = False
                    break
            rule_results.append({
                "rule_code": "RULE_007",
                "rule_name": "票据日期逻辑检查",
                "passed": all_dates_valid,
                "actual_value": f"事故日期: {accident_date.strftime('%Y-%m-%d') if accident_date else 'N/A'}",
                "expected_value": "所有票据日期晚于事故日期",
                "description": "检查票据日期是否在事故发生之后",
                "severity": "warning" if not all_dates_valid else "info"
            })

        return rule_results


class MockRiskAnalyzer:
    HIGH_RISK_DIAGNOSES = ["癌症", "白血病", "心脏病", "脑中风", "尿毒症"]
    HIGH_RISK_AMOUNT_THRESHOLD = 50000.0
    FREQUENT_CLAIM_THRESHOLD = 3

    @staticmethod
    def analyze(case_data: Dict[str, Any], rule_results: List[Dict[str, Any]],
                ocr_results: List[Dict[str, Any]], historical_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        risk_alerts = []
        total_risk_score = 0.0

        claim_amount = case_data.get("claim_amount", 0)
        if claim_amount >= MockRiskAnalyzer.HIGH_RISK_AMOUNT_THRESHOLD:
            contribution = min(30, (claim_amount / MockRiskAnalyzer.HIGH_RISK_AMOUNT_THRESHOLD) * 10)
            total_risk_score += contribution
            risk_alerts.append({
                "alert_code": "RISK_001",
                "alert_type": "amount_risk",
                "title": "高额索赔风险",
                "description": f"索赔金额{claim_amount}元超过高风险阈值{MockRiskAnalyzer.HIGH_RISK_AMOUNT_THRESHOLD}元",
                "risk_level": "high",
                "risk_score_contribution": contribution,
                "evidence": {"claim_amount": claim_amount, "threshold": MockRiskAnalyzer.HIGH_RISK_AMOUNT_THRESHOLD},
                "explanation": f"根据规则，索赔金额超过{MockRiskAnalyzer.HIGH_RISK_AMOUNT_THRESHOLD}元的案件被标记为高风险，需要人工重点审核。",
                "recommendation": "建议由资深理赔人员审核，核实费用真实性。"
            })

        failed_rules = [r for r in rule_results if not r.get("passed") and r.get("severity") == "error"]
        if len(failed_rules) >= 2:
            contribution = len(failed_rules) * 5
            total_risk_score += contribution
            risk_alerts.append({
                "alert_code": "RISK_002",
                "alert_type": "rule_violation",
                "title": "多项规则校验不通过",
                "description": f"共有{len(failed_rules)}项严重规则校验未通过",
                "risk_level": "high",
                "risk_score_contribution": contribution,
                "evidence": {"failed_rules": [r["rule_name"] for r in failed_rules]},
                "explanation": "多项关键规则校验失败，可能存在材料不完整或信息不一致问题。",
                "recommendation": "请检查补充相关材料，或说明特殊情况。"
            })

        diagnoses = [r.get("diagnosis", "") for r in ocr_results if r.get("diagnosis")]
        high_risk_diagnoses = [d for d in diagnoses if any(hr in d for hr in MockRiskAnalyzer.HIGH_RISK_DIAGNOSES)]
        if high_risk_diagnoses:
            contribution = 25
            total_risk_score += contribution
            risk_alerts.append({
                "alert_code": "RISK_003",
                "alert_type": "medical_risk",
                "title": "重大疾病风险",
                "description": f"诊断涉及高风险疾病: {', '.join(high_risk_diagnoses)}",
                "risk_level": "critical",
                "risk_score_contribution": contribution,
                "evidence": {"diagnoses": diagnoses, "high_risk_diagnoses": high_risk_diagnoses},
                "explanation": "诊断结果包含重大疾病列表中的疾病，此类案件通常赔付金额高，需严格核查。",
                "recommendation": "建议核查完整病历，确认保险责任范围，必要时进行医疗调查。"
            })

        if len(historical_cases) >= MockRiskAnalyzer.FREQUENT_CLAIM_THRESHOLD:
            recent_cases = [c for c in historical_cases if (datetime.now() - c.get("claim_date", datetime.now())).days <= 180]
            if len(recent_cases) >= MockRiskAnalyzer.FREQUENT_CLAIM_THRESHOLD:
                contribution = 20
                total_risk_score += contribution
                risk_alerts.append({
                    "alert_code": "RISK_004",
                    "alert_type": "frequency_risk",
                    "title": "频繁索赔风险",
                    "description": f"该被保险人近180天内已索赔{len(recent_cases)}次",
                    "risk_level": "high",
                    "risk_score_contribution": contribution,
                    "evidence": {"claim_count_180d": len(recent_cases), "threshold": MockRiskAnalyzer.FREQUENT_CLAIM_THRESHOLD},
                    "explanation": "短期内多次索赔可能存在过度医疗或保险欺诈风险。",
                    "recommendation": "建议核查历史索赔记录，确认是否存在重复索赔或过度医疗情况。"
                })

        document_hashes = [hashlib.md5(r.get("recognized_text", "").encode()).hexdigest() for r in ocr_results]
        if len(document_hashes) != len(set(document_hashes)):
            contribution = 30
            total_risk_score += contribution
            duplicates = [h for h in document_hashes if document_hashes.count(h) > 1]
            risk_alerts.append({
                "alert_code": "RISK_005",
                "alert_type": "duplicate_document",
                "title": "重复单据风险",
                "description": "检测到重复提交的单据",
                "risk_level": "critical",
                "risk_score_contribution": contribution,
                "evidence": {"duplicate_count": len(duplicates), "duplicate_hashes": list(set(duplicates))},
                "explanation": "系统检测到内容高度相似的重复单据，可能存在重复索赔风险。",
                "recommendation": "请仔细核对所有单据，移除重复提交的材料，并说明原因。"
            })

        name_mismatches = [r for r in rule_results if r.get("rule_code") == "RULE_001" and not r.get("passed")]
        if name_mismatches:
            contribution = 15
            total_risk_score += contribution
            risk_alerts.append({
                "alert_code": "RISK_006",
                "alert_type": "identity_mismatch",
                "title": "身份信息不一致",
                "description": "索赔人与被保险人信息不一致",
                "risk_level": "medium",
                "risk_score_contribution": contribution,
                "evidence": {"details": name_mismatches[0].get("actual_value", "")},
                "explanation": "索赔人信息与被保险人信息存在差异，需确认是否为合法受益人。",
                "recommendation": "请提供相关证明文件，确认索赔资格。"
            })

        if total_risk_score >= 80:
            risk_level = "critical"
        elif total_risk_score >= 50:
            risk_level = "high"
        elif total_risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_alerts": risk_alerts,
            "overall_risk_level": risk_level,
            "overall_risk_score": round(total_risk_score, 2),
            "is_high_risk": total_risk_score >= 50
        }
