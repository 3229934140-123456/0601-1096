import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://localhost:8000"

def test_root():
    print("=" * 60)
    print("测试 1: 根路径")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/")
    data = json.loads(response.read().decode())
    print(f"应用名称: {data['app']}")
    print(f"版本: {data['version']}")
    print(f"状态: {data['status']}")
    print(f"API文档: {data['docs']}")
    print("[OK] 通过")
    return data

def test_health():
    print("\n" + "=" * 60)
    print("测试 2: 健康检查")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/health")
    data = json.loads(response.read().decode())
    print(f"状态: {data['status']}")
    print("[OK] 通过")
    return data

def test_list_cases():
    print("\n" + "=" * 60)
    print("测试 3: 案件列表")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/cases")
    data = json.loads(response.read().decode())
    print(f"共 {len(data)} 个案件")
    for case in data:
        print(f"  {case['case_no']}: {case['claimant_name']} - "
              f"{case['claim_amount']}元 - 风险: {case['risk_level']} - "
              f"状态: {case['status']}")
    print("[OK] 通过")
    return data

def test_create_case():
    print("\n" + "=" * 60)
    print("测试 4: 创建新案件")
    print("=" * 60)
    case_data = {
        "case_no": f"CL{int(time.time())}",
        "policy_no": "POLTEST001",
        "claimant_name": "测试用户",
        "claimant_id_card": "110101199001011234",
        "insured_name": "测试用户",
        "insured_id_card": "110101199001011234",
        "claim_amount": 15000.0,
        "accident_date": "2024-06-01T00:00:00"
    }
    req = urllib.request.Request(
        f"{BASE_URL}/api/cases",
        data=json.dumps(case_data).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"案件ID: {data['id']}")
    print(f"案件号: {data['case_no']}")
    print(f"状态: {data['status']}")
    print("[OK] 通过")
    return data

def test_case_detail(case_id):
    print("\n" + "=" * 60)
    print("测试 5: 案件详情")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/cases/{case_id}")
    data = json.loads(response.read().decode())
    print(f"案件号: {data['case_no']}")
    print(f"索赔人: {data['claimant_name']}")
    print(f"文档数: {len(data['documents'])}")
    print(f"OCR结果数: {len(data['ocr_results'])}")
    print(f"规则检查数: {len(data['rule_checks'])}")
    print(f"风险预警数: {len(data['risk_alerts'])}")
    print("[OK] 通过")
    return data

def test_ocr_recognize_all(case_id):
    print("\n" + "=" * 60)
    print("测试 6: 批量OCR识别")
    print("=" * 60)
    req = urllib.request.Request(
        f"{BASE_URL}/api/ocr/case/{case_id}/recognize-all",
        data=json.dumps({}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"识别完成，共 {len(data)} 个OCR结果")
    for result in data[:2]:
        print(f"  文档 {result['document_id']}: 金额 {result['recognized_amount']}元, "
              f"置信度 {result['confidence']:.2%}")
    print("[OK] 通过")
    return data

def test_extraction(case_id):
    print("\n" + "=" * 60)
    print("测试 7: 文本抽取")
    print("=" * 60)
    req = urllib.request.Request(
        f"{BASE_URL}/api/extraction/extract",
        data=json.dumps({"case_id": case_id}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"{data['message']}")
    print(f"抽取数据: {len(data['extracted_data'])} 条")
    for item in data['extracted_data'][:3]:
        print(f"  {item['key']}: {item['value']} (置信度: {item['confidence']:.2%})")
    print("[OK] 通过")
    return data

def test_rule_check(case_id):
    print("\n" + "=" * 60)
    print("测试 8: 规则核对")
    print("=" * 60)
    req = urllib.request.Request(
        f"{BASE_URL}/api/rules/check",
        data=json.dumps({"case_id": case_id}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"{data['message']}")
    print(f"全部通过: {data['all_passed']}")
    passed = sum(1 for r in data['rule_checks'] if r['passed'])
    print(f"规则通过: {passed}/{len(data['rule_checks'])}")
    for rule in data['rule_checks']:
        status = "[OK]" if rule['passed'] else "[FAIL]"
        print(f"  {status} [{rule['severity']}] {rule['rule_name']}: {rule['actual_value']}")
    print("[OK] 通过")
    return data

def test_risk_analysis(case_id):
    print("\n" + "=" * 60)
    print("测试 9: 风险分析")
    print("=" * 60)
    req = urllib.request.Request(
        f"{BASE_URL}/api/risk/analyze",
        data=json.dumps({"case_id": case_id}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"{data['message']}")
    print(f"风险等级: {data['overall_risk_level']}")
    print(f"风险得分: {data['overall_risk_score']}")
    print(f"高风险标记: {data['is_high_risk']}")
    print(f"风险预警: {len(data['risk_alerts'])} 条")
    for alert in data['risk_alerts']:
        print(f"  [{alert['risk_level']}] {alert['title']}: {alert['description']}")
        if alert['explanation']:
            print(f"    说明: {alert['explanation']}")
        if alert['recommendation']:
            print(f"    建议: {alert['recommendation']}")
    print("[OK] 通过")
    return data

def test_progress(case_id):
    print("\n" + "=" * 60)
    print("测试 10: 进度查询")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/progress/{case_id}")
    data = json.loads(response.read().decode())
    print(f"案件号: {data['case_no']}")
    print(f"当前状态: {data['status_description']}")
    print(f"处理进度: {data['progress_percent']}% ({data['current_step']}/{data['total_steps']})")
    print(f"补件项: {len(data['supplement_items'])} 项")
    if data['estimated_completion_time']:
        print(f"预计完成: {data['estimated_completion_time']}")
    print("[OK] 通过")
    return data

def test_supplement_list(case_id):
    print("\n" + "=" * 60)
    print("测试 11: 补件清单")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/progress/{case_id}/supplement-list")
    data = json.loads(response.read().decode())
    print(f"案件号: {data['case_no']}")
    print(f"索赔人: {data['claimant_name']}")
    print(f"补件项数: {data['items_count']}")
    print(f"截止日期: {data['deadline']}")
    for item in data['items']:
        print(f"  [{item['priority']}] {item['item_name']}: {item['description']}")
        if item['reason']:
            print(f"    原因: {item['reason']}")
    print("[OK] 通过")
    return data

def test_reviewers():
    print("\n" + "=" * 60)
    print("测试 12: 复核人列表")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/review/reviewers")
    data = json.loads(response.read().decode())
    print(f"共 {len(data)} 位复核人")
    for r in data:
        print(f"  {r['employee_no']}: {r['name']} - {r['department']} - {r['level']}")
    print("[OK] 通过")
    return data

def test_export_summary(case_id):
    print("\n" + "=" * 60)
    print("测试 13: 导出审查摘要")
    print("=" * 60)
    req = urllib.request.Request(
        f"{BASE_URL}/api/result/export",
        data=json.dumps({"case_id": case_id, "format": "json"}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())
    print(f"{data['message']}")
    print(f"文件名: {data['file_name']}")
    print(f"下载链接: {data['file_url']}")
    if data['summary']:
        print(f"摘要包含: 基本信息, {len(data['summary']['documents'])}个文档, "
              f"{len(data['summary']['ocr_recognition'])}个OCR结果, "
              f"{len(data['summary']['risk_analysis']['alerts'])}个风险预警")
        conclusion = data['summary']['conclusion']
        print(f"审核结论: {conclusion['conclusion']}")
        print(f"处理建议: {conclusion['recommendation']}")
    print("[OK] 通过")
    return data

def test_call_logs(case_id):
    print("\n" + "=" * 60)
    print("测试 14: 调用日志")
    print("=" * 60)
    response = urllib.request.urlopen(f"{BASE_URL}/api/progress/{case_id}/logs")
    data = json.loads(response.read().decode())
    print(f"共 {len(data)} 条调用记录")
    for log in data[:5]:
        print(f"  [{log['created_at']}] {log['api_method']} {log['api_endpoint']} "
              f"- 状态: {log['status_code']} - 耗时: {log['processing_time_ms']}ms")
    print("[OK] 通过")
    return data

def main():
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "保险理赔材料初审AI平台 API 测试" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print(f"\n测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务地址: {BASE_URL}")

    try:
        test_root()
        test_health()
        cases = test_list_cases()

        if cases:
            test_case = cases[0]
            case_id = test_case['id']
            print(f"\n使用测试案件: {test_case['case_no']} (ID: {case_id})")

            test_case_detail(case_id)
            test_ocr_recognize_all(case_id)
            test_extraction(case_id)
            test_rule_check(case_id)
            test_risk_analysis(case_id)
            test_progress(case_id)
            test_supplement_list(case_id)
            test_reviewers()
            test_export_summary(case_id)
            test_call_logs(case_id)

        test_create_case()

        print("\n" + "=" * 60)
        print("[OK] 所有测试通过！")
        print("=" * 60)
        print(f"\nAPI文档地址: {BASE_URL}/docs")
        print(f"可交互Swagger UI已在浏览器中打开")
        print("\n支持的8类接口:")
        print("  1. 案件提交 - /api/cases")
        print("  2. 图片识别 - /api/ocr")
        print("  3. 文本抽取 - /api/extraction")
        print("  4. 规则核对 - /api/rules")
        print("  5. 风险提示 - /api/risk")
        print("  6. 人工复核 - /api/review")
        print("  7. 进度查询 - /api/progress")
        print("  8. 结果回传 - /api/result")

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
