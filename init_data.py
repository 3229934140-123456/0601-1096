from database import SessionLocal, engine, Base
from models import Reviewer, ClaimCase, Document, ClaimStatus, DocumentType
from datetime import datetime, timedelta
import os
from config import settings


def init_database():
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成")

    db = SessionLocal()

    try:
        reviewers = [
            {"employee_no": "R001", "name": "王经理", "department": "理赔部", "level": "senior"},
            {"employee_no": "R002", "name": "李主管", "department": "理赔部", "level": "intermediate"},
            {"employee_no": "R003", "name": "张专员", "department": "理赔部", "level": "junior"},
            {"employee_no": "R004", "name": "刘专员", "department": "理赔部", "level": "junior"},
        ]

        for rev_data in reviewers:
            existing = db.query(Reviewer).filter(Reviewer.employee_no == rev_data["employee_no"]).first()
            if not existing:
                reviewer = Reviewer(**rev_data)
                db.add(reviewer)
                print(f"创建复核人: {rev_data['name']}")

        db.commit()

        test_cases = [
            {
                "case_no": "CL20240001",
                "policy_no": "POL123456789",
                "claimant_name": "张三",
                "claimant_id_card": "110101199001011234",
                "insured_name": "张三",
                "insured_id_card": "110101199001011234",
                "claim_amount": 25000.0,
                "accident_date": datetime.now() - timedelta(days=15)
            },
            {
                "case_no": "CL20240002",
                "policy_no": "POL987654321",
                "claimant_name": "李四",
                "claimant_id_card": "310101198505055678",
                "insured_name": "李四",
                "insured_id_card": "310101198505055678",
                "claim_amount": 85000.0,
                "accident_date": datetime.now() - timedelta(days=7)
            },
            {
                "case_no": "CL20240003",
                "policy_no": "POL111222333",
                "claimant_name": "王五",
                "claimant_id_card": "440101199212129012",
                "insured_name": "王五",
                "insured_id_card": "440101199212129012",
                "claim_amount": 5000.0,
                "accident_date": datetime.now() - timedelta(days=3)
            }
        ]

        for case_data in test_cases:
            existing = db.query(ClaimCase).filter(ClaimCase.case_no == case_data["case_no"]).first()
            if not existing:
                case = ClaimCase(**case_data)
                db.add(case)
                db.flush()
                print(f"创建测试案件: {case_data['case_no']}")

                doc_types = [DocumentType.ID_CARD, DocumentType.INVOICE, DocumentType.POLICY]
                for i, doc_type in enumerate(doc_types):
                    file_name = f"{case_data['case_no']}_{doc_type.value}_{i+1}.jpg"
                    file_path = settings.UPLOAD_DIR / file_name

                    with open(file_path, "w") as f:
                        f.write(f"Mock {doc_type.value} document for {case_data['case_no']}")

                    doc = Document(
                        case_id=case.id,
                        document_type=doc_type,
                        file_name=file_name,
                        file_path=str(file_path),
                        file_size=1024 * (i + 1),
                        file_hash=f"hash_{case_data['case_no']}_{i}"
                    )
                    db.add(doc)
                    print(f"  创建文档: {file_name}")

        db.commit()
        print("测试数据初始化完成")

    except Exception as e:
        db.rollback()
        print(f"初始化失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
