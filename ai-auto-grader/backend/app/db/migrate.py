"""轻量 schema 迁移。

本项目未引入 Alembic，`Base.metadata.create_all` 只建新表、不会给已有表补列，
因此这里用幂等的 `ALTER TABLE ADD COLUMN` 为存量数据库补齐新增字段。
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# (表名, 列名, 列定义) —— 新增列统一登记在这里，启动时自动补齐
COLUMN_PATCHES = [
    ("answer_card_templates", "source_type", "VARCHAR(16) DEFAULT 'generated' NOT NULL"),
    ("answer_card_templates", "orientation", "VARCHAR(16) DEFAULT 'portrait' NOT NULL"),
    ("answer_card_templates", "page_sizes", "JSON"),
    ("template_regions", "group_key", "VARCHAR(64)"),
    ("template_regions", "option_spec", "JSON"),
    ("imported_pages", "name_ocr", "VARCHAR(64)"),
    ("imported_pages", "class_ocr", "VARCHAR(64)"),
    ("precheck_pages", "name_ocr", "VARCHAR(64)"),
    ("precheck_pages", "class_ocr", "VARCHAR(64)"),
]


def run_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied = []
    for table, column, ddl in COLUMN_PATCHES:
        if table not in existing_tables:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if column in columns:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        applied.append(f"{table}.{column}")
    if applied:
        logger.info("schema 迁移完成: %s", ", ".join(applied))