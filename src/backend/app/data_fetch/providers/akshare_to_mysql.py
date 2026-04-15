"""
Akshare data provider for data fetch operations
"""

import logging
import os
import queue
import time
import uuid
from threading import Thread
from typing import Any

import akshare as ak
import pandas as pd

from app.data_fetch.core.mysql_base import MysqlBase
from app.data_fetch.utils.common_utils import retry_on_exception


class FuncThread(Thread):
    """Thread for executing function with timeout"""

    def __init__(self, func, *args, **kwargs):
        Thread.__init__(self)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result = queue.Queue()
        self.exc = None

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.result.put(("success", result))
        except Exception as e:
            self.result.put(("error", str(e)))

    def get_result(self, timeout=None):
        try:
            return self.result.get(timeout=timeout)
        except queue.Empty:
            return ("timeout", None)


class AkshareToMySql(MysqlBase):
    """Akshare数据提供者，实现特定方法"""

    def __init__(self, db_config: dict[str, Any], logger: logging.Logger | None = None):
        super().__init__(db_config, logger or logging.getLogger("AkshareToMySql"))
        self.contract_units = {
            # 吨
            "cu": "吨",
            "bc": "吨",
            "al": "吨",
            "zn": "吨",
            "pb": "吨",
            "ni": "吨",
            "sn": "吨",
            "rb": "吨",
            "wr": "吨",
            "hc": "吨",
            "nr": "吨",
            "ao": "吨",
            "bu": "吨",
            "sp": "吨",
            "ss": "吨",
            # 克
            "au": "克",
            # 千克
            "ag": "千克",
            # 桶
            "sc": "桶",
            "lu": "桶",
            "fu": "桶",
        }
        self.max_retries = 3
        self.retry_delay = 5

    @retry_on_exception(max_retries=10, retry_delay=5)
    def fetch_ak_data(self, function_name, *args, **kwargs):
        """
        通用方法，用于从Akshare获取数据

        Args:
            function_name: Akshare函数名
            *args, **kwargs: 函数的参数

        Returns:
            pd.DataFrame: 获取的数据
        """
        try:
            call_timeout_s = kwargs.pop("_call_timeout", None)
            if call_timeout_s is None:
                # Default AKShare call timeout. Can be overridden per-call via `_call_timeout`
                # or globally via env `AKSHARE_CALL_TIMEOUT`.
                call_timeout_s = int(os.getenv("AKSHARE_CALL_TIMEOUT", "120"))
            else:
                call_timeout_s = int(call_timeout_s)

            func = getattr(ak, function_name)
            self.logger.info(f"调用Akshare函数: {function_name}")

            thread = FuncThread(func, *args, **kwargs)
            thread.daemon = True
            thread.start()

            status, result = thread.get_result(timeout=call_timeout_s)

            if status == "success":
                if isinstance(result, pd.DataFrame):
                    self.logger.info(f"获取数据成功，共{len(result)}行")
                else:
                    self.logger.info(f"获取数据成功，类型: {type(result)}")
                return result
            elif status == "timeout":
                raise TimeoutError(f"Function call timed out after {call_timeout_s} seconds")
            else:
                raise Exception(result)

        except TimeoutError as te:
            self.logger.error(f"获取数据超时: {te}")
            raise
        except AttributeError:
            self.logger.error(f"Akshare中不存在函数: {function_name}")
            raise
        except Exception as e:
            self.logger.error(f"从Akshare获取数据失败: {e}")
            raise

    def save_to_mysql(
        self,
        df: "pd.DataFrame",
        table_name: str,
        on_duplicate_update: bool = False,
        unique_keys: "list[str] | None" = None,
    ) -> bool:
        """save_data 的别名，供自动生成脚本调用。若表不存在则先用 create_table_sql 建表。"""
        import uuid as _uuid

        create_sql = getattr(self, "create_table_sql", None)
        if create_sql:
            try:
                self.connect_db()
                self.cursor.execute(create_sql)
                self.connection.commit()
            except Exception as e:
                self.logger.warning(f"建表失败（可能已存在）: {e}")

        # 若表要求 R_ID 但 DataFrame 中没有，自动生成 UUID
        if "R_ID" not in df.columns:
            try:
                self.connect_db()
                self.cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE 'R_ID'")
                if self.cursor.fetchone():
                    df = df.copy()
                    df.insert(0, "R_ID", [_uuid.uuid4().hex.upper() for _ in range(len(df))])
            except Exception as e:
                self.logger.debug("Skip R_ID auto-insert for %s: %s", table_name, e)

        return self.save_data(
            df, table_name, on_duplicate_update=on_duplicate_update, unique_keys=unique_keys
        )

    def get_uuid(self):
        """生成UUID"""
        return str(uuid.uuid4()).replace("-", "").upper()

    def get_trading_day_list(
        self, start_date: str, end_date: str, exchange: str = "XSHG"
    ) -> list[str]:
        """
        获取指定交易所和时间范围内的交易日列表
        """
        table_name = "trading_days"

        try:
            if self.table_exists(table_name):
                self.connect_db()
                query = f"""  # nosec B608
                SELECT trading_day FROM {table_name}
                WHERE exchange = %s AND trading_day BETWEEN %s AND %s
                ORDER BY trading_day
                """
                self.cursor.execute(query, (exchange, start_date, end_date))
                results = self.cursor.fetchall()

                if results:
                    trading_days = [
                        (row[0].strftime("%Y-%m-%d") if hasattr(row[0], "strftime") else row[0])
                        for row in results
                    ]
                    self.logger.info(f"从数据库获取到{len(trading_days)}个交易日")
                    return trading_days
        except Exception as e:
            self.logger.warning(f"从数据库获取交易日失败: {e}")

        # 使用pandas_market_calendars作为备选
        try:
            import pandas_market_calendars as mcal

            exchange_map = {
                "XSHG": "SSE",
                "XSHE": "SZSE",
                "DCE": "DCE",
                "SHFE": "SHFE",
                "CZCE": "CZCE",
                "CFFEX": "CFFEX",
                "INE": "INE",
                "GFEX": "GFEX",
            }

            mcal_exchange = exchange_map.get(exchange, "SSE")
            calendar = mcal.get_calendar(mcal_exchange)
            schedule = calendar.schedule(start_date=start_date, end_date=end_date)
            trading_days = schedule.index.strftime("%Y-%m-%d").tolist()

            self.logger.info(f"使用pandas_market_calendars获取到{len(trading_days)}个交易日")
            return trading_days

        except Exception as e:
            self.logger.error(f"获取交易日列表失败: {e}")
            raise

    def get_future_symbol_list(self):
        """获取期货品种列表"""
        try:
            self.connect_db()
            query = """
                    SELECT DISTINCT(PRODUCT_CODE) FROM FUTURES_TRADING_FEES
                    """
            self.cursor.execute(query)
            results = self.cursor.fetchall()
            if results:
                symbol_list = [row[0] for row in results]
                self.logger.info("从数据库成功获取交易品种")
                return symbol_list
        except Exception as e:
            self.logger.warning(f"从数据库获取失败: {e}")
        finally:
            self.disconnect_db()

    def get_current_futures_contract_list(self):
        """获取所有当前交易的期货合约代码"""
        futures_symbol_mark_df = self.fetch_ak_data("futures_symbol_mark")

        big_df = pd.DataFrame()
        for item in futures_symbol_mark_df["symbol"]:
            time.sleep(0.2)
            futures_zh_realtime_df = self.fetch_ak_data("futures_zh_realtime", item)
            big_df = pd.concat([big_df, futures_zh_realtime_df], ignore_index=True)
        return big_df["symbol"].tolist()

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
