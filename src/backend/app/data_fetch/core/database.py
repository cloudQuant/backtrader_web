"""
Database base class for data fetch operations
"""

import logging
from datetime import date, datetime, timedelta
from types import TracebackType
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pytz


class Database:
    def __init__(self, db_config: dict[str, Any], logger: logging.Logger | None = None):
        self.db_config = db_config
        self.logger = logger or logging.getLogger("DBBase")
        self.connection = None
        self.cursor = None
        self.batch_size = 1000

    def _setup_logging(self, name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def connect_db(self) -> None:
        raise NotImplementedError

    def disconnect_db(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "Database":
        self.connect_db()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.disconnect_db()

    def _execute_batch(self, insert_sql: str, batch: list[Any]) -> None:
        raise NotImplementedError

    def save_data(
        self,
        df: pd.DataFrame,
        table_name: str,
        on_duplicate_update: bool = False,
        unique_keys: list[str] | None = None,
    ) -> bool:
        raise NotImplementedError

    def delete_data(self, table_name: str, conditions: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_current_datetime(self) -> str:
        """获取当前日期时间字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_current_date(self) -> str:
        """获取当前日期字符串"""
        return datetime.now().strftime("%Y-%m-%d")

    def get_previous_date(self, tz: str = "Asia/Shanghai") -> str:
        """获取指定时区的前一天日期"""
        try:
            timezone = pytz.timezone(tz)
            now = datetime.now(timezone)
            previous_day = now - timedelta(days=1)
            return previous_day.strftime("%Y-%m-%d")
        except Exception as e:
            self.logger.error(f"日期计算失败: {str(e)}")
            raise

    def get_next_date(
        self, base_date: date | datetime | str | None = None, tz: str = "Asia/Shanghai"
    ) -> str:
        """获取指定时区的后一天日期"""
        try:
            if base_date is None:
                timezone = pytz.timezone(tz)
                now = datetime.now(timezone)
                next_day = now + timedelta(days=1)
            else:
                if isinstance(base_date, (datetime, date)):
                    # Ensure we work with datetime for strftime compatibility
                    if isinstance(base_date, datetime):
                        next_day = base_date + timedelta(days=1)
                    else:  # date
                        # Convert date to datetime, then add timedelta
                        temp_datetime = datetime.combine(base_date, datetime.min.time())
                        next_day = temp_datetime + timedelta(days=1)
                else:
                    date_str = str(base_date).strip()
                    date_formats = ["%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y.%m.%d"]
                    parsed_date = None
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    if parsed_date is None:
                        raise ValueError(f"不支持的日期格式: {base_date}")
                    next_day = parsed_date + timedelta(days=1)
            return next_day.strftime("%Y-%m-%d")
        except Exception as e:
            self.logger.error(f"日期计算失败: {str(e)}")
            raise

    def get_previous_month(self) -> str:
        """获取上个月，格式YYYYMM"""
        today = datetime.now()
        first_day_of_prev_month = today.replace(day=1) - timedelta(days=1)
        return first_day_of_prev_month.strftime("%Y%m")

    def get_current_month(self) -> str:
        """获取当前月份，格式YYYYMM"""
        today = datetime.now()
        return today.strftime("%Y%m")

    def get_next_month(self, base_month: str | date | datetime | None = None) -> str:
        """获取下个月，格式YYYYMM"""
        try:
            if base_month is None:
                base_month = self.get_current_month()

            if isinstance(base_month, (datetime, date)):
                # Convert date to datetime if needed for replace() compatibility
                if isinstance(base_month, datetime):
                    base_date = base_month
                else:  # date
                    base_date = datetime.combine(base_month, datetime.min.time())
            else:
                date_str = str(base_month).strip()
                date_formats = ["%Y%m", "%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
                base_date = None
                for fmt in date_formats:
                    try:
                        base_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if base_date is None:
                    raise ValueError(f"不支持的日期格式: {base_month}")

            assert base_date is not None  # Type narrow for mypy
            if base_date.month == 12:
                next_month = base_date.replace(year=base_date.year + 1, month=1, day=1)
            else:
                next_month = base_date.replace(month=base_date.month + 1, day=1)

            return next_month.strftime("%Y%m")
        except Exception as e:
            self.logger.error(f"获取下个月份失败: {str(e)}")
            raise
