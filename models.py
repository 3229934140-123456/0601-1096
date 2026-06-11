from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from database import Base


class ClaimStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    OCR_PROCESSING = "ocr_processing"
    OCR_COMPLETED = "ocr_completed"
    EXTRACTION_PROCESSING = "extraction_processing"
    EXTRACTION_COMPLETED = "extraction_completed"
    RULE_CHECKING = "rule_checking"
    RULE_CHECKED = "rule_checked"
    RISK_ANALYZING = "risk_analyzing"
    RISK_ANALYZED = "risk_analyzed"
    PENDING_REVIEW = "pending_review"
    REVIEWING = "reviewing"
    REVIEWED = "reviewed"
    SUPPLEMENT_REQUESTED = "supplement_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    COMPLETED = "completed"


class DocumentType(str, enum.Enum):
    POLICY = "policy"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    MEDICAL_RECORD = "medical_record"
    ID_CARD = "id_card"
    BANK_CARD = "bank_card"
    ACCIDENT_PROOF = "accident_proof"
    OTHER = "other"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewResult(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEED_SUPPLEMENT = "need_supplement"
    NEED_REINVESTIGATION = "need_reinvestigation"


class ClaimCase(Base):
    __tablename__ = "claim_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_no = Column(String(64), unique=True, index=True, nullable=False)
    policy_no = Column(String(64), index=True)
    claimant_name = Column(String(128))
    claimant_id_card = Column(String(32))
    insured_name = Column(String(128))
    insured_id_card = Column(String(32))
    claim_amount = Column(Float, default=0.0)
    accident_date = Column(DateTime)
    claim_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(ClaimStatus), default=ClaimStatus.SUBMITTED)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW)
    risk_score = Column(Float, default=0.0)
    is_high_risk = Column(Boolean, default=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"))
    review_result = Column(Enum(ReviewResult))
    review_opinion = Column(Text)
    review_date = Column(DateTime)
    final_approved_amount = Column(Float)
    supplement_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_data = Column(JSON, default={})

    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    ocr_results = relationship("OCRResult", back_populates="case", cascade="all, delete-orphan")
    extracted_data = relationship("ExtractedData", back_populates="case", cascade="all, delete-orphan")
    rule_checks = relationship("RuleCheckResult", back_populates="case", cascade="all, delete-orphan")
    risk_alerts = relationship("RiskAlert", back_populates="case", cascade="all, delete-orphan")
    review_records = relationship("ReviewRecord", back_populates="case", cascade="all, delete-orphan")
    supplement_items = relationship("SupplementItem", back_populates="case", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="case")
    reviewer = relationship("Reviewer", back_populates="cases")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer)
    file_hash = Column(String(64))
    upload_time = Column(DateTime, default=datetime.utcnow)
    is_duplicate = Column(Boolean, default=False)
    duplicate_with = Column(Integer)
    ocr_completed = Column(Boolean, default=False)
    extra_data = Column(JSON, default={})

    case = relationship("ClaimCase", back_populates="documents")
    ocr_results = relationship("OCRResult", back_populates="document", cascade="all, delete-orphan")


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    recognized_text = Column(Text)
    confidence = Column(Float, default=0.0)
    recognized_amount = Column(Float)
    recognized_date = Column(DateTime)
    recognized_name = Column(String(128))
    recognized_id_card = Column(String(32))
    invoice_no = Column(String(64))
    hospital_name = Column(String(255))
    diagnosis = Column(String(512))
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})

    case = relationship("ClaimCase", back_populates="ocr_results")
    document = relationship("Document", back_populates="ocr_results")


class ExtractedData(Base):
    __tablename__ = "extracted_data"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    source_type = Column(String(64))
    key = Column(String(128), nullable=False)
    value = Column(Text)
    value_type = Column(String(32))
    confidence = Column(Float, default=0.0)
    extracted_from = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})

    case = relationship("ClaimCase", back_populates="extracted_data")


class RuleCheckResult(Base):
    __tablename__ = "rule_check_results"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    rule_code = Column(String(64), nullable=False)
    rule_name = Column(String(255), nullable=False)
    passed = Column(Boolean, default=False)
    actual_value = Column(Text)
    expected_value = Column(Text)
    description = Column(Text)
    severity = Column(String(32), default="warning")
    suggestion = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})

    case = relationship("ClaimCase", back_populates="rule_checks")


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    alert_code = Column(String(64), nullable=False)
    alert_type = Column(String(64))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    risk_score_contribution = Column(Float, default=0.0)
    evidence = Column(JSON, default={})
    explanation = Column(Text)
    recommendation = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("ClaimCase", back_populates="risk_alerts")


class Reviewer(Base):
    __tablename__ = "reviewers"

    id = Column(Integer, primary_key=True, index=True)
    employee_no = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    department = Column(String(128))
    level = Column(String(32), default="junior")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})

    cases = relationship("ClaimCase", back_populates="reviewer")
    review_records = relationship("ReviewRecord", back_populates="reviewer")


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"), nullable=False)
    action = Column(String(64), nullable=False)
    opinion = Column(Text)
    result = Column(Enum(ReviewResult))
    approved_amount = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})

    case = relationship("ClaimCase", back_populates="review_records")
    reviewer = relationship("Reviewer", back_populates="review_records")


class SupplementItem(Base):
    __tablename__ = "supplement_items"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"), nullable=False)
    item_code = Column(String(64), nullable=False)
    item_name = Column(String(255), nullable=False)
    description = Column(Text)
    reason = Column(Text)
    priority = Column(Integer, default=1)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("ClaimCase", back_populates="supplement_items")


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("claim_cases.id"))
    api_endpoint = Column(String(255), nullable=False)
    api_method = Column(String(16), nullable=False)
    request_data = Column(JSON, default={})
    response_data = Column(JSON, default={})
    status_code = Column(Integer)
    processing_time_ms = Column(Integer)
    caller_ip = Column(String(64))
    caller_agent = Column(String(512))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("ClaimCase", back_populates="call_logs")
