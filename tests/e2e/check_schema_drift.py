#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库 schema 漂移检测脚本

对比 SQLAlchemy 模型 (Base.metadata) 与实际 MySQL 数据库 schema，
找出模型中有但数据库表中缺失的列/表。用于定位迁移未同步导致的 500 错误。

Usage:
    python tests/e2e/check_schema_drift.py            # 仅检测
    python tests/e2e/check_schema_drift.py --fix       # 检测并添加缺失列 (nullable=True)
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend"))

from dotenv import load_dotenv
load_dotenv()

import pymysql
from sqlalchemy import JSON, Float, Integer, String, DateTime, Text, Boolean, Numeric
from app.config import get_settings
from app.db.database import Base
# 触发所有模型注册
import app.models  # noqa: F401

settings = get_settings()
import re
m = re.search(r"://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.DATABASE_URL)
user, password, host, port, database = m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5)


def sqlalchemy_type_for(col):
    """返回 MySQL DDL 类型字符串"""
    t = col.type
    if isinstance(t, Float):
        return "FLOAT"
    if isinstance(t, Integer):
        return "INT"
    if isinstance(t, (JSON,)):
        return "JSON"
    if isinstance(t, Text):
        return "TEXT"
    if isinstance(t, DateTime):
        return "DATETIME"
    if isinstance(t, Boolean):
        return "TINYINT(1)"
    if isinstance(t, Numeric):
        return f"DECIMAL({t.precision or 10},{t.scale or 2})"
    # String
    length = getattr(t, "length", None) or 255
    return f"VARCHAR({length})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="添加缺失的列 (nullable=True)")
    args = parser.parse_args()

    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
    cur = conn.cursor()

    cur.execute("SHOW TABLES")
    existing_tables = {r[0] for r in cur.fetchall()}

    missing_tables = []
    missing_columns = []  # (table, col_name, ddl)

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            missing_tables.append(table_name)
            continue
        cur.execute("DESCRIBE `%s`" % table_name)
        actual_cols = {r[0] for r in cur.fetchall()}
        for col in table.columns:
            if col.name not in actual_cols:
                ddl = sqlalchemy_type_for(col)
                missing_columns.append((table_name, col.name, ddl))

    print("=" * 70)
    print("Schema 漂移检测报告")
    print("=" * 70)
    print(f"缺失表: {len(missing_tables)}")
    for t in missing_tables:
        print(f"  - {t}")
    print(f"缺失列: {len(missing_columns)}")
    for table, col, ddl in missing_columns:
        print(f"  - {table}.{col}  ({ddl})")

    if args.fix and missing_columns:
        print("\n" + "-" * 70)
        print("应用修复 (添加缺失列, nullable=True)...")
        for table, col, ddl in missing_columns:
            try:
                sql = f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl} NULL"
                cur.execute(sql)
                print(f"  ✓ {table}.{col}")
            except Exception as e:
                print(f"  ✗ {table}.{col}: {e}")
        conn.commit()

    if args.fix and missing_tables:
        print("\n缺失表不会自动创建（需通过模型 create_all 或迁移）。")

    conn.close()


if __name__ == "__main__":
    main()
