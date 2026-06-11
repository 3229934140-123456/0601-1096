from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from database import engine, Base
from middleware import CallLogMiddleware
from routers import (
    case_submission,
    ocr_recognition,
    text_extraction,
    rule_checking,
    risk_analysis,
    manual_review,
    progress_query,
    result_callback,
    batch_processing
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from migrations import run_migrations
    run_migrations()
    print("数据库迁移完成")
    
    from init_data import init_database
    init_database()
    
    print(f"上传目录: {settings.UPLOAD_DIR.absolute()}")
    print(f"导出目录: {settings.EXPORT_DIR.absolute()}")
    yield
    print("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="保险理赔材料初审AI应用平台后端服务",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CallLogMiddleware)

app.include_router(case_submission.router)
app.include_router(ocr_recognition.router)
app.include_router(text_extraction.router)
app.include_router(rule_checking.router)
app.include_router(risk_analysis.router)
app.include_router(manual_review.router)
app.include_router(progress_query.router)
app.include_router(result_callback.router)
app.include_router(batch_processing.router)


@app.get("/", tags=["系统"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api_endpoints": {
            "case_submission": "/api/cases",
            "ocr_recognition": "/api/ocr",
            "text_extraction": "/api/extraction",
            "rule_checking": "/api/rules",
            "risk_analysis": "/api/risk",
            "manual_review": "/api/review",
            "progress_query": "/api/progress",
            "result_callback": "/api/result",
            "batch_processing": "/api/batch"
        }
    }


@app.get("/health", tags=["系统"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": {
            "utc": datetime.utcnow().isoformat()
        }
    }


from datetime import datetime

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
