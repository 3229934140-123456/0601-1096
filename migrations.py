from sqlalchemy import text, inspect, Column, Integer, String, Float, DateTime, Text, Boolean, JSON
from database import engine, Base, SessionLocal
from models import (
    ClaimCase, Document, OCRResult, ExtractedData, RuleCheckResult,
    RiskAlert, Reviewer, ReviewRecord, SupplementItem, CallLog,
    SummaryVersion, BatchTask
)
from datetime import datetime
import os

SCHEMA_VERSION = 4
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

TABLE_MODELS = [
    ClaimCase, Document, OCRResult, ExtractedData, RuleCheckResult,
    RiskAlert, Reviewer, ReviewRecord, SupplementItem, CallLog,
    SummaryVersion, BatchTask
]


def get_current_version(db) -> int:
    try:
        result = db.execute(text("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"))
        row = result.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def set_version(db, version: int, description: str):
    db.execute(
        text("INSERT INTO schema_version (version, description, applied_at) VALUES (:v, :d, :t)"),
        {"v": version, "d": description, "t": datetime.utcnow()}
    )
    db.commit()


def ensure_schema_version_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at DATETIME NOT NULL
        )
    """))
    db.commit()


def column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def get_column_type_sql(column) -> str:
    col_type = type(column.type).__name__
    type_map = {
        "Integer": "INTEGER",
        "SmallInteger": "INTEGER",
        "BigInteger": "INTEGER",
        "String": "VARCHAR",
        "Text": "TEXT",
        "Float": "REAL",
        "DateTime": "DATETIME",
        "Date": "DATE",
        "Boolean": "BOOLEAN",
        "JSON": "JSON",
        "Enum": "VARCHAR",
    }
    sql_type = type_map.get(col_type, "TEXT")
    if hasattr(column.type, "length") and column.type.length:
        sql_type = f"VARCHAR({column.type.length})"
    return sql_type


def get_column_default_sql(column) -> str:
    if column.default is None:
        return None
    arg = column.default.arg
    if callable(arg):
        return None
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str):
        return f"'{arg}'"
    if isinstance(arg, dict):
        return "'{}'"
    if isinstance(arg, list):
        return "'[]'"
    return None


def sync_table_columns(db, model_class):
    table_name = model_class.__tablename__
    if not table_exists(table_name):
        return []

    inspector = inspect(engine)
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}

    added = []
    for col in model_class.__table__.columns:
        if col.name in existing_cols:
            continue
        if col.primary_key:
            continue

        col_type = get_column_type_sql(col)
        default_sql = get_column_default_sql(col)
        nullable = "" if col.nullable else " NOT NULL"

        ddl = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}"
        if default_sql is not None:
            ddl += f" DEFAULT {default_sql}"
        ddl += nullable

        try:
            db.execute(text(ddl))
            db.commit()
            added.append(col.name)
        except Exception as e:
            db.rollback()
            print(f"  [WARN] 添加字段 {table_name}.{col.name} 失败: {e}")

    return added


def migrate_v1_to_v2(db):
    if not column_exists("rule_check_results", "suggestion"):
        db.execute(text("ALTER TABLE rule_check_results ADD COLUMN suggestion TEXT"))
    if not column_exists("rule_check_results", "manual_status"):
        db.execute(text("ALTER TABLE rule_check_results ADD COLUMN manual_status VARCHAR(32) DEFAULT 'unconfirmed'"))
    if not column_exists("rule_check_results", "manual_note"):
        db.execute(text("ALTER TABLE rule_check_results ADD COLUMN manual_note TEXT"))
    if not column_exists("rule_check_results", "manual_confirmed_by"):
        db.execute(text("ALTER TABLE rule_check_results ADD COLUMN manual_confirmed_by VARCHAR(128)"))
    if not column_exists("rule_check_results", "manual_confirmed_at"):
        db.execute(text("ALTER TABLE rule_check_results ADD COLUMN manual_confirmed_at DATETIME"))
    db.commit()


def migrate_v2_to_v3(db):
    if not table_exists("summary_versions"):
        db.execute(text("""
            CREATE TABLE summary_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES claim_cases(id),
                version INTEGER NOT NULL,
                format VARCHAR(16) DEFAULT 'json',
                file_name VARCHAR(255),
                file_path VARCHAR(512),
                generated_by VARCHAR(128) DEFAULT 'system',
                generated_at DATETIME,
                summary_snapshot JSON DEFAULT '{}',
                is_latest BOOLEAN DEFAULT 1,
                extra_data JSON DEFAULT '{}'
            )
        """))

    if not table_exists("batch_tasks"):
        db.execute(text("""
            CREATE TABLE batch_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_no VARCHAR(64) UNIQUE NOT NULL,
                task_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) DEFAULT 'pending',
                triggered_by VARCHAR(128) DEFAULT 'system',
                filter_status VARCHAR(64),
                case_ids JSON DEFAULT '[]',
                total_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                results JSON DEFAULT '[]',
                started_at DATETIME,
                completed_at DATETIME,
                created_at DATETIME,
                extra_data JSON DEFAULT '{}'
            )
        """))
    db.commit()


def migrate_v3_to_v4(db):
    print("[DB Migration] 执行通用字段对齐，检查所有表...")
    total_added = 0
    for model in TABLE_MODELS:
        table_name = model.__tablename__
        if not table_exists(table_name):
            continue
        added = sync_table_columns(db, model)
        if added:
            print(f"  {table_name}: 新增 {len(added)} 个字段 -> {', '.join(added)}")
            total_added += len(added)
    if total_added == 0:
        print("  所有表字段已对齐，无需新增")
    db.commit()


def run_migrations():
    db = SessionLocal()
    try:
        ensure_schema_version_table(db)
        current = get_current_version(db)
        print(f"[DB Migration] 当前 schema 版本: v{current}, 目标版本: v{SCHEMA_VERSION}")

        if current < 1:
            Base.metadata.create_all(bind=engine)
            set_version(db, 1, "初始 schema: 创建所有基础表")
            current = 1
            print("[DB Migration] 已升级到 v1: 基础表结构")

        if current < 2:
            migrate_v1_to_v2(db)
            set_version(db, 2, "规则核对增强: 新增 suggestion, manual_* 字段")
            current = 2
            print("[DB Migration] 已升级到 v2: 规则核对 suggestion 和人工确认字段")

        if current < 3:
            migrate_v2_to_v3(db)
            set_version(db, 3, "新增审查摘要版本表和批量任务表")
            current = 3
            print("[DB Migration] 已升级到 v3: summary_versions 和 batch_tasks")

        if current < 4:
            migrate_v3_to_v4(db)
            set_version(db, 4, "通用字段对齐: 所有表缺失字段自动补齐")
            current = 4
            print("[DB Migration] 已升级到 v4: 全表字段自动对齐")

        if current == SCHEMA_VERSION:
            print(f"[DB Migration] Schema 已是最新版本 v{SCHEMA_VERSION}")

    except Exception as e:
        print(f"[DB Migration] 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()
