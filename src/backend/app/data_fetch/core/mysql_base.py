"""
MySQL base class for database operations
"""

import logging
from datetime import datetime
from typing import Any

import mysql.connector
import pandas as pd

from app.data_fetch.core.database import Database


class MysqlBase(Database):
    """数据库连接和操作基类"""

    def __init__(self, db_config: dict[str, Any], logger: logging.Logger | None = None):
        super().__init__(db_config, logger)
        self.db_config = db_config
        self.logger = logger or self._setup_logging("MysqlBase")

    def connect_db(self):
        """建立数据库连接"""
        try:
            if not self.connection or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**self.db_config)
                self.cursor = self.connection.cursor()
                self.logger.info("数据库连接成功")
        except mysql.connector.Error as err:
            self.logger.error(f"数据库连接失败: {err}")
            raise

    def disconnect_db(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.connection = None
            self.logger.info("数据库连接已关闭")

    def _auto_create_table(self, table_name: str, df: "pd.DataFrame") -> None:
        """根据 DataFrame 的列和类型自动建表（若表已存在则跳过）"""
        type_map = {
            "int64": "BIGINT",
            "int32": "INT",
            "int16": "SMALLINT",
            "int8": "TINYINT",
            "uint64": "BIGINT UNSIGNED",
            "uint32": "INT UNSIGNED",
            "float64": "DOUBLE",
            "float32": "FLOAT",
            "bool": "TINYINT(1)",
            "datetime64[ns]": "DATETIME",
            "object": "TEXT",
        }
        col_defs = []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            mysql_type = type_map.get(dtype_str, "TEXT")
            esc = col.replace("`", "``")
            col_defs.append(f"  `{esc}` {mysql_type}")
        cols_sql = ",\n".join(col_defs)
        create_sql = f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n{cols_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        try:
            self.cursor.execute(create_sql)
            self.connection.commit()
            self.logger.info(f"自动建表成功: {table_name}")
        except mysql.connector.Error as err:
            self.logger.warning(f"自动建表失败 {table_name}: {err}")

    def _execute_batch(self, insert_sql, batch):
        """执行批量插入或更新操作"""
        try:
            self.cursor.executemany(insert_sql, batch)
            self.connection.commit()
            return True
        except mysql.connector.Error as err:
            self.connection.rollback()
            self.logger.error(f"批量执行失败: {err}")
            raise

    def save_data(
        self,
        df: pd.DataFrame,
        table_name: str,
        on_duplicate_update: bool = False,
        unique_keys: list[str] = None,
        ignore_duplicates: bool = False,
    ) -> bool:
        """将DataFrame保存到数据库表"""
        if df.empty:
            self.logger.warning(f"DataFrame为空，无需保存到 {table_name}")
            return False

        # Some AkShare endpoints occasionally return unnamed columns (NaN/None/empty).
        # MySQL will interpret them as column `nan` and fail. Drop/normalize defensively.
        raw_cols = list(df.columns)
        valid_idx: list[int] = []
        normalized_cols: list[str] = []
        dropped: list[str] = []
        for idx, col in enumerate(raw_cols):
            if col is None:
                dropped.append("<None>")
                continue
            # pandas can carry np.nan in column labels
            if isinstance(col, float) and pd.isna(col):
                dropped.append("nan")
                continue
            col_str = str(col).strip()
            if not col_str or col_str.lower() == "nan":
                dropped.append(col_str or "<empty>")
                continue
            valid_idx.append(idx)
            normalized_cols.append(col_str)

        if dropped:
            self.logger.warning(f"表 {table_name} 将丢弃 {len(dropped)} 个无效列名: {dropped[:10]}")

        if not valid_idx:
            self.logger.warning(f"表 {table_name} 所有列名均无效，跳过保存")
            return False

        df = df.iloc[:, valid_idx].copy()
        df.columns = normalized_cols

        self.connect_db()

        safe_table = str(table_name).replace("`", "``")

        # 若表不存在则根据 DataFrame 自动建表
        try:
            self.cursor.execute(f"SHOW TABLES LIKE '{safe_table}'")
            if not self.cursor.fetchone():
                self._auto_create_table(safe_table, df)
        except mysql.connector.Error as err:
            self.logger.warning(f"检查表 {table_name} 是否存在时出错: {err}")

        # Align DataFrame columns to actual table schema to avoid "Unknown column" errors.
        # This is best-effort: if schema introspection fails, we fall back to raw df columns.
        # MySQL column names are case-insensitive, so build a case-insensitive mapping.
        try:
            self.cursor.execute(f"SHOW COLUMNS FROM `{safe_table}`")
            table_rows = self.cursor.fetchall() or []
            # Build case-insensitive mapping: lowercase table column -> actual table column name
            table_cols_ci = {row[0].lower(): row[0] for row in table_rows}
            if table_cols_ci:
                # Build mapping from df column name -> actual table column name (case-insensitive match)
                column_mapping = {}
                unknown = []
                for c in df.columns:
                    c_lower = str(c).lower()
                    if c_lower in table_cols_ci:
                        column_mapping[c] = table_cols_ci[c_lower]
                    else:
                        unknown.append(c)
                if unknown:
                    self.logger.warning(
                        f"表 {table_name} 将忽略 {len(unknown)} 个不存在的列: {unknown[:10]}"
                    )
                if not column_mapping:
                    self.logger.warning(
                        f"表 {table_name} 无可写入的有效列（df列都不在表结构中），跳过保存"
                    )
                    return False
                # Rename df columns to match actual table column names
                df = df.rename(columns=column_mapping).copy()
            else:
                self.logger.warning(
                    f"表 {table_name} SHOW COLUMNS 返回空结果，将按 df 列名直接写入"
                )
        except mysql.connector.Error as err:
            self.logger.warning(f"无法读取表 {table_name} 字段列表，将按 df 列名直接写入: {err}")

        # Final guard: never try to write an unnamed/nan column.
        bad_cols = [
            c for c in df.columns if str(c).strip().lower() == "nan" or str(c).strip() == ""
        ]
        if bad_cols:
            self.logger.warning(f"表 {table_name} 检测到非法列名 {bad_cols[:10]}，将移除后继续写入")
            df = df[[c for c in df.columns if c not in bad_cols]].copy()
            if df.empty or not list(df.columns):
                self.logger.warning(f"表 {table_name} 移除非法列名后无可写入列，跳过保存")
                return False

        cols = list(df.columns)
        quoted_cols = [f"`{str(col).replace('`', '``')}`" for col in cols]
        placeholders = ", ".join(["%s"] * len(cols))

        cols_str = ", ".join(quoted_cols)

        if ignore_duplicates:
            insert_sql = f"INSERT IGNORE INTO `{safe_table}` ({cols_str}) VALUES ({placeholders})"  # nosec B608
        elif on_duplicate_update and unique_keys:
            insert_sql = f"INSERT INTO `{safe_table}` ({cols_str}) VALUES ({placeholders})"  # nosec B608
        else:
            insert_sql = f"INSERT INTO `{safe_table}` ({cols_str}) VALUES ({placeholders})"  # nosec B608

        if on_duplicate_update and unique_keys and not ignore_duplicates:
            update_clauses = []
            for col in cols:
                if col not in unique_keys:
                    esc = str(col).replace("`", "``")
                    update_clauses.append(f"`{esc}`=VALUES(`{esc}`)")
            if update_clauses:
                insert_sql += f" ON DUPLICATE KEY UPDATE {', '.join(update_clauses)}"

        # mysql-connector may serialize NaN as bare token `nan` which MySQL treats as an identifier,
        # yielding "Unknown column 'nan' in 'field list'". Convert all NaN/NaT/NA to None first.
        df = df.astype(object).where(pd.notnull(df), None)
        values = df.values.tolist()
        total_rows = len(values)

        try:
            start_time = datetime.now()
            processed = 0

            for i in range(0, total_rows, self.batch_size):
                batch = values[i : i + self.batch_size]
                self._execute_batch(insert_sql, batch)
                processed += len(batch)

                if (i + self.batch_size) % (self.batch_size * 10) == 0 or (
                    i + self.batch_size
                ) >= total_rows:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    self.logger.info(
                        f"已处理 {processed}/{total_rows} 行 ({processed / total_rows * 100:.1f}%)，"
                        f"耗时 {elapsed:.2f}s"
                    )

            end_time = datetime.now()
            elapsed_seconds = (end_time - start_time).total_seconds()

            self.logger.info(
                f"成功保存 {total_rows} 行数据到 {table_name}，耗时 {elapsed_seconds:.2f}s"
            )

            return total_rows

        except Exception as e:
            self.logger.error(f"保存数据到 {table_name} 失败: {str(e)}")
            raise

    def delete_data(self, table_name: str, conditions: dict[str, Any]):
        """根据条件从数据库表中删除数据"""
        if not conditions:
            self.logger.error("删除操作必须提供条件，禁止无条件删除")
            return False

        self.connect_db()

        where_clauses = []
        values = []

        for col, val in conditions.items():
            where_clauses.append(f"{col} = %s")
            values.append(val)

        where_str = " AND ".join(where_clauses)
        delete_sql = f"DELETE FROM {table_name} WHERE {where_str}"  # nosec B608

        try:
            self.cursor.execute(delete_sql, values)
            deleted_rows = self.cursor.rowcount
            self.connection.commit()
            self.logger.info(f"从表 {table_name} 删除了 {deleted_rows} 行记录")
            return True
        except mysql.connector.Error as err:
            self.connection.rollback()
            self.logger.error(f"从表 {table_name} 删除数据失败: {err}")
            raise

    def get_one_column_from_table(self, column_name: str, table_name: str):
        """从表中获取单个列的所有值"""
        self.connect_db()
        try:
            query = f"SELECT DISTINCT {column_name} FROM {table_name}"  # nosec B608
            self.cursor.execute(query)
            results = self.cursor.fetchall()
            return [row[0] for row in results]
        except mysql.connector.Error as err:
            self.logger.error(f"获取 {table_name}.{column_name} 失败: {err}")
            return []

    def get_latest_date(
        self,
        table_name: str,
        date_column: str = "BASEDATE",
        conditions: dict[str, Any] = None,
    ):
        """获取表中指定日期列的最新日期"""
        self.connect_db()
        try:
            if conditions is None or not conditions:
                query = f"SELECT MAX({date_column}) FROM {table_name}"  # nosec B608
                params = None
            else:
                where_conditions = []
                params = []
                for key, value in conditions.items():
                    where_conditions.append(f"{key} = %s")
                    params.append(value)
                where_clause = " AND ".join(where_conditions)
                query = f"SELECT MAX({date_column}) FROM {table_name} WHERE {where_clause}"  # nosec B608

            self.cursor.execute(query, params)
            result = self.cursor.fetchone()[0]

            if result:
                if isinstance(result, datetime):
                    return result.strftime("%Y-%m-%d")
                return str(result)
            else:
                return None
        except mysql.connector.Error as err:
            self.logger.error(f"获取表 {table_name} 的最新日期失败: {err}")
            return None

    def safe_date_format(self, series) -> pd.Series:
        """安全格式化日期序列"""
        datetime_series = pd.to_datetime(series, errors="coerce")
        formatted = datetime_series.apply(
            lambda x: x.strftime("%Y-%m-%d") if not pd.isnull(x) else None
        )
        return formatted

    def table_exists(self, table_name: str) -> bool:
        """检查数据库中是否存在指定的表"""
        try:
            self.connect_db()
            self.cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            result = self.cursor.fetchone()
            return result is not None
        except mysql.connector.Error as err:
            self.logger.error(f"检查表 {table_name} 是否存在时出错: {err}")
            return False
        finally:
            self.disconnect_db()

    def create_table(self, create_table_sql: str):
        """创建表"""
        try:
            self.connect_db()
            self.cursor.execute(create_table_sql)
            self.connection.commit()
            self.logger.info("成功创建表")
            return True
        except mysql.connector.Error as err:
            self.logger.error(f"创建表失败: {err}")
            if self.connection:
                self.connection.rollback()
            return False
        finally:
            self.disconnect_db()

    def create_table_if_not_exists(
        self, table_name: str = None, create_table_sql: str = None
    ) -> bool:
        """Compatibility helper used by many scripts."""
        tname = table_name or getattr(self, "table_name", None)
        ddl = create_table_sql or getattr(self, "create_table_sql", None)
        if not tname or not ddl:
            self.logger.warning("create_table_if_not_exists 缺少 table_name/create_table_sql，跳过")
            return False
        if not self.table_exists(tname):
            return bool(self.create_table(ddl))
        return False

    def create_table_from_dataframe_if_not_exists(
        self,
        *,
        table_name: str,
        df: pd.DataFrame,
        primary_key: str = "R_ID",
        add_fetched_at: bool = True,
    ) -> bool:
        """
        Create a MySQL table from a DataFrame schema when scripts don't provide explicit DDL.

        This is intentionally conservative: most columns become TEXT to avoid type-mismatch issues.
        """
        if df is None or getattr(df, "empty", True):
            self.logger.warning(
                "create_table_from_dataframe_if_not_exists: df empty; skip create table=%s",
                table_name,
            )
            return False

        if len(str(table_name)) > 64:
            raise ValueError(f"MySQL table_name too long (>64): {table_name!r}")
        if "\x00" in str(table_name):
            raise ValueError("MySQL table_name contains NUL byte")

        # Caller should ensure df.columns are already safe/unique and <= 64 chars each.
        for c in list(df.columns):
            if len(str(c)) > 64:
                raise ValueError(f"MySQL column name too long (>64): {c!r}")
            if "\x00" in str(c):
                raise ValueError("MySQL column contains NUL byte")

        # Build DDL.
        def _sql_type_for_series(s: pd.Series) -> str:
            try:
                if pd.api.types.is_bool_dtype(s):
                    return "TINYINT(1)"
                if pd.api.types.is_integer_dtype(s):
                    return "BIGINT"
                if pd.api.types.is_float_dtype(s):
                    return "DOUBLE"
                if pd.api.types.is_datetime64_any_dtype(s):
                    return "DATETIME"
            except Exception as e:
                self.logger.debug("_sql_type_for_series fallback to TEXT: %s", e)
            return "TEXT"

        cols_sql: list[str] = []
        pk = str(primary_key)
        cols_sql.append(f"`{pk.replace('`', '``')}` VARCHAR(64) NOT NULL")
        if add_fetched_at:
            cols_sql.append("`FETCHED_AT` DATETIME NULL")
        for col in list(df.columns):
            series = df[col]
            sql_type = _sql_type_for_series(series)
            cols_sql.append(f"`{str(col).replace('`', '``')}` {sql_type} NULL")

        ddl = (
            f"CREATE TABLE IF NOT EXISTS `{str(table_name).replace('`', '``')}` ("
            + ", ".join(cols_sql)
            + f", PRIMARY KEY (`{pk.replace('`', '``')}`)"
            + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )

        try:
            self.connect_db()
            self.cursor.execute(ddl)
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error("Failed to create table from df: %s, error=%s", table_name, e)
            if self.connection:
                self.connection.rollback()
            raise
        finally:
            self.disconnect_db()

    def get_data_by_columns(
        self, table_name: str, column_list: list, where_condition: str = None
    ) -> pd.DataFrame:
        """从指定表中获取指定列的数据"""
        if not column_list:
            self.logger.warning("列名列表不能为空")
            return pd.DataFrame()

        cursor = None
        try:
            self.connect_db()
            cursor = self.connection.cursor()

            columns = ", ".join(column_list)
            query = f"SELECT {columns} FROM {table_name}"  # nosec B608

            if where_condition:
                query += f" WHERE {where_condition}"

            self.logger.debug(f"执行查询: {query}")

            cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            if rows:
                df = pd.DataFrame(rows, columns=columns)
                self.logger.info(f"成功从 {table_name} 获取 {len(df)} 行数据")
            else:
                df = pd.DataFrame(columns=columns)
                self.logger.warning(f"表 {table_name} 中没有找到匹配的数据")

            return df

        except Exception as e:
            self.logger.error(f"查询表 {table_name} 失败: {e}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()
            self.disconnect_db()

    def parse_numeric(self, value):
        """Convert string to float, handling None and empty strings"""
        try:
            if pd.isna(value) or value == "":
                return None
            return float(str(value).replace(",", ""))
        except Exception as _e:
            self.logger.warning(f"Error parsing numeric value {value}: {_e}")
            return None

    def query_data(self, query: str, params: tuple | None = None):
        """
        Execute a SELECT query and return results

        Args:
            query: SQL query string
            params: Optional query parameters

        Returns:
            Query results as list of tuples
        """
        try:
            self.connect_db()
            self.cursor.execute(query, params or ())
            return self.cursor.fetchall()
        except mysql.connector.Error as err:
            self.logger.error(f"Query failed: {err}")
            return None
        finally:
            self.disconnect_db()

    def insert_data(self, df: pd.DataFrame, table_name: str, columns: list[str] | None = None):
        """
        Insert DataFrame data into database table

        Args:
            df: DataFrame to insert
            table_name: Target table name
            columns: List of column names to insert

        Returns:
            bool: True if successful
        """
        try:
            if df.empty:
                self.logger.warning("DataFrame is empty, nothing to insert")
                return False

            # Use save_data method if columns are not specified
            if columns is None:
                return self.save_data(df, table_name)

            # Build INSERT statement
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"  # nosec B608

            # Prepare data
            data = df[columns].values.tolist()

            self.connect_db()
            self.cursor.executemany(insert_sql, data)
            self.connection.commit()
            self.logger.info(f"Inserted {len(data)} rows into {table_name}")
            return True

        except mysql.connector.Error as err:
            self.connection.rollback()
            self.logger.error(f"Insert failed: {err}")
            return False
        finally:
            self.disconnect_db()

    def execute_sql(
        self,
        sql: str,
        params: tuple | None = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ):
        """
        Execute arbitrary SQL statement

        Args:
            sql: SQL statement
            params: Optional parameters
            fetch_one: If True, return first row of results
            fetch_all: If True, return all rows of results

        Returns:
            bool: True if successful (when no fetch requested)
            tuple: First row if fetch_one=True
            list: All rows if fetch_all=True
            None: On error or no results
        """
        try:
            self.connect_db()
            self.cursor.execute(sql, params or ())

            if fetch_one:
                result = self.cursor.fetchone()
                return result
            elif fetch_all:
                result = self.cursor.fetchall()
                return result
            else:
                self.connection.commit()
                return True

        except mysql.connector.Error as err:
            if not (fetch_one or fetch_all):
                self.connection.rollback()
            self.logger.error(f"Execute SQL failed: {err}")
            return None
        finally:
            self.disconnect_db()
