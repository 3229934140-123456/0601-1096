from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "保险理赔材料初审AI平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./insurance_claims.db"

    UPLOAD_DIR: Path = Path("./uploads")
    EXPORT_DIR: Path = Path("./exports")

    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    OCR_SERVICE_URL: str = "http://mock-ocr-service/recognize"
    NLP_SERVICE_URL: str = "http://mock-nlp-service/extract"

    HIGH_RISK_AMOUNT_THRESHOLD: float = 50000.0
    DUPLICATE_DETECTION_WINDOW_DAYS: int = 30

    class Config:
        env_file = ".env"


settings = Settings()

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
