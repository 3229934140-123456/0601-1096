from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from models import ClaimStatus, DocumentType, RiskLevel, ReviewResult, RuleManualStatus, BatchTaskStatus, BatchTaskType


class CaseBase(BaseModel):
    policy_no: Optional[str] = None
    claimant_name: Optional[str] = None
    claimant_id_card: Optional[str] = None
    insured_name: Optional[str] = None
    insured_id_card: Optional[str] = None
    claim_amount: Optional[float] = 0.0
    accident_date: Optional[datetime] = None


class CaseCreate(CaseBase):
    case_no: str


class CaseUpdate(BaseModel):
    policy_no: Optional[str] = None
    claimant_name: Optional[str] = None
    claimant_id_card: Optional[str] = None
    insured_name: Optional[str] = None
    insured_id_card: Optional[str] = None
    claim_amount: Optional[float] = None
    accident_date: Optional[datetime] = None
    status: Optional[ClaimStatus] = None
    extra_data: Optional[Dict[str, Any]] = None


class CaseResponse(CaseBase):
    id: int
    case_no: str
    status: ClaimStatus
    risk_level: RiskLevel
    risk_score: float
    is_high_risk: bool
    reviewer_id: Optional[int] = None
    review_result: Optional[ReviewResult] = None
    final_approved_amount: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CaseDetailResponse(CaseResponse):
    documents: List["DocumentResponse"] = []
    ocr_results: List["OCRResultResponse"] = []
    extracted_data: List["ExtractedDataResponse"] = []
    rule_checks: List["RuleCheckResponse"] = []
    risk_alerts: List["RiskAlertResponse"] = []
    review_records: List["ReviewRecordResponse"] = []
    supplement_items: List["SupplementItemResponse"] = []


class DocumentBase(BaseModel):
    document_type: DocumentType
    file_name: str


class DocumentResponse(DocumentBase):
    id: int
    case_id: int
    file_path: str
    file_size: Optional[int] = None
    upload_time: datetime
    is_duplicate: bool
    ocr_completed: bool

    class Config:
        from_attributes = True


class OCRResultBase(BaseModel):
    recognized_text: Optional[str] = None
    confidence: float = 0.0
    recognized_amount: Optional[float] = None
    recognized_date: Optional[datetime] = None
    recognized_name: Optional[str] = None
    recognized_id_card: Optional[str] = None
    invoice_no: Optional[str] = None
    hospital_name: Optional[str] = None
    diagnosis: Optional[str] = None


class OCRResultResponse(OCRResultBase):
    id: int
    case_id: int
    document_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ExtractedDataResponse(BaseModel):
    id: int
    case_id: int
    source_type: Optional[str] = None
    key: str
    value: Optional[str] = None
    value_type: Optional[str] = None
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True


class RuleCheckBase(BaseModel):
    rule_code: str
    rule_name: str
    passed: bool
    actual_value: Optional[str] = None
    expected_value: Optional[str] = None
    description: Optional[str] = None
    severity: str = "warning"
    suggestion: Optional[str] = None


class RuleCheckResponse(RuleCheckBase):
    id: int
    case_id: int
    manual_status: RuleManualStatus = RuleManualStatus.UNCONFIRMED
    manual_note: Optional[str] = None
    manual_confirmed_by: Optional[str] = None
    manual_confirmed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RiskAlertBase(BaseModel):
    alert_code: str
    alert_type: Optional[str] = None
    title: str
    description: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_score_contribution: float = 0.0
    evidence: Dict[str, Any] = {}
    explanation: Optional[str] = None
    recommendation: Optional[str] = None


class RiskAlertResponse(RiskAlertBase):
    id: int
    case_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewerBase(BaseModel):
    employee_no: str
    name: str
    department: Optional[str] = None
    level: str = "junior"


class ReviewerResponse(ReviewerBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewRecordBase(BaseModel):
    action: str
    opinion: Optional[str] = None
    result: Optional[ReviewResult] = None
    approved_amount: Optional[float] = None


class ReviewRecordResponse(ReviewRecordBase):
    id: int
    case_id: int
    reviewer_id: int
    reviewer_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SupplementItemBase(BaseModel):
    item_code: str
    item_name: str
    description: Optional[str] = None
    reason: Optional[str] = None
    priority: int = 1


class SupplementItemResponse(SupplementItemBase):
    id: int
    case_id: int
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CallLogResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    api_endpoint: str
    api_method: str
    status_code: Optional[int] = None
    processing_time_ms: Optional[int] = None
    caller_ip: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OCRRequest(BaseModel):
    document_id: int
    case_id: int


class OCRResponse(BaseModel):
    success: bool
    message: str
    ocr_result: Optional[OCRResultResponse] = None


class ExtractionRequest(BaseModel):
    case_id: int
    ocr_result_id: Optional[int] = None


class ExtractionResponse(BaseModel):
    success: bool
    message: str
    extracted_data: List[ExtractedDataResponse] = []


class RuleCheckRequest(BaseModel):
    case_id: int


class RuleCheckSummaryResponse(BaseModel):
    success: bool
    message: str
    rule_checks: List["RuleCheckResponse"] = []
    all_passed: bool = False


class RiskAnalysisRequest(BaseModel):
    case_id: int


class RuleStatsSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    effective_failed: int = 0
    false_positive_count: int = 0
    confirmed_count: int = 0
    need_supplement_count: int = 0
    unconfirmed_count: int = 0
    pass_rate: float = 0.0


class RiskAnalysisResponse(BaseModel):
    success: bool
    message: str
    risk_alerts: List[RiskAlertResponse] = []
    overall_risk_level: RiskLevel
    overall_risk_score: float
    is_high_risk: bool
    rule_stats: Optional[RuleStatsSummary] = None
    recommendation: Optional[str] = None
    conclusion: Optional[str] = None
    manual_processed: Optional[bool] = None


class AssignReviewerRequest(BaseModel):
    case_id: int
    reviewer_id: int


class ReviewSubmitRequest(BaseModel):
    case_id: int
    result: ReviewResult
    opinion: Optional[str] = None
    approved_amount: Optional[float] = None
    supplement_items: List[SupplementItemBase] = []


class WithdrawCaseRequest(BaseModel):
    case_id: int
    reason: Optional[str] = None


class ProgressResponse(BaseModel):
    case_id: int
    case_no: str
    status: ClaimStatus
    status_description: str
    current_step: int
    total_steps: int
    progress_percent: float
    estimated_completion_time: Optional[datetime] = None
    supplement_items: List[SupplementItemResponse] = []
    timeline: List[Dict[str, Any]] = []


class ExportRequest(BaseModel):
    case_id: int
    format: str = "pdf"


class ExportResponse(BaseModel):
    success: bool
    message: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None


class ResultCallbackRequest(BaseModel):
    case_id: int
    callback_url: str
    callback_data: Optional[Dict[str, Any]] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


CaseDetailResponse.model_rebuild()


class RuleManualConfirmRequest(BaseModel):
    rule_check_id: int
    manual_status: RuleManualStatus
    manual_note: Optional[str] = None
    confirmed_by: Optional[str] = None


class SummaryVersionResponse(BaseModel):
    id: int
    case_id: int
    version: int
    format: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    generated_by: str
    generated_at: datetime
    is_latest: bool
    summary_snapshot: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class SummaryExportRequest(BaseModel):
    case_id: int
    format: str = "json"
    generated_by: Optional[str] = "system"


class BatchProcessRequest(BaseModel):
    task_type: BatchTaskType = BatchTaskType.FULL_PIPELINE
    status_filter: Optional[ClaimStatus] = None
    case_ids: Optional[List[int]] = None
    triggered_by: Optional[str] = "system"


class BatchCaseResult(BaseModel):
    case_id: int
    case_no: str
    success: bool
    message: str
    stage: Optional[str] = None
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    final_status: Optional[str] = None

    class Config:
        from_attributes = True


class BatchTaskResponse(BaseModel):
    task_id: int
    task_no: str
    task_type: BatchTaskType
    status: BatchTaskStatus
    total_count: int
    success_count: int
    failed_count: int
    results: List[BatchCaseResult] = []
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
