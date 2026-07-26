import re
import time
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

DEFAULT_MAX_SYMBOLS = 5
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_SYMBOLS = ["AG", "CU"]
RANK_BUCKETS = (5, 10, 15, 20)


class FuturesRankSumDaily(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_RANK_SUM_DAILY"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_RANK_SUM_DAILY (
                                    R_ID VARCHAR(36) NOT NULL COMMENT 'UUID生成的唯一标识',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据的名称代码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据的中文名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据的日期',
                                    CREATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建日期',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                    UPDATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日期',
                                    UPDATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                    VARIETY_CODE VARCHAR(10) NOT NULL COMMENT '合约代码',
                                    VARIETY_NAME VARCHAR(50) NOT NULL COMMENT '品种代码',
                                    RANK_TYPE VARCHAR(20) NOT NULL COMMENT '排名类型(top5/top10/top15/top20)',
                                    RANK_NUM INT NOT NULL COMMENT '排名数量',
                                    TOTAL_VOL BIGINT COMMENT '总成交量',
                                    TOTAL_LONG_POSITION BIGINT COMMENT '总多头持仓',
                                    TOTAL_SHORT_POSITION BIGINT COMMENT '总空头持仓',
                                    VOL_CHANGE BIGINT COMMENT '成交量变化',
                                    LONG_POSITION_CHANGE BIGINT COMMENT '多头持仓变化',
                                    SHORT_POSITION_CHANGE BIGINT COMMENT '空头持仓变化',
                                    PRIMARY KEY (R_ID),
                                    UNIQUE KEY uk_rank_sum (BASEDATE, VARIETY_CODE, RANK_TYPE),
                                    KEY idx_basedate (BASEDATE),
                                    KEY idx_variety (VARIETY_CODE),
                                    KEY idx_rank_type (RANK_TYPE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='期货会员持仓排名汇总表';
                                """

    @staticmethod
    def _normalize_symbol_list(symbols):
        if symbols is None:
            return []
        if isinstance(symbols, str):
            raw_symbols = re.split(r"[,;，；\s]+", symbols)
        else:
            raw_symbols = symbols

        normalized = []
        seen = set()
        for item in raw_symbols:
            if item is None:
                continue
            symbol = str(item).strip().upper()
            if not symbol or not re.fullmatch(r"[A-Z]+", symbol):
                continue
            if symbol not in seen:
                normalized.append(symbol)
                seen.add(symbol)
        return normalized

    @staticmethod
    def _coerce_int(value):
        numeric_value = pd.to_numeric(value, errors="coerce")
        if pd.isna(numeric_value):
            return None
        return int(numeric_value)

    @staticmethod
    def _format_source_date(value):
        parsed = pd.to_datetime(str(value), errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.strftime("%Y-%m-%d")

    @staticmethod
    def _lookback_start(current_date, lookback_days):
        parsed = datetime.strptime(current_date.replace("-", ""), "%Y%m%d")
        return (parsed - timedelta(days=lookback_days)).strftime("%Y%m%d")

    def _transform_rank_sum_dataframe(self, df, reference_code):
        rows = []
        for _, source_row in df.iterrows():
            contract_code = str(source_row.get("symbol", "")).strip().upper()
            variety_code = str(source_row.get("variety", reference_code)).strip().upper()
            base_date = self._format_source_date(source_row.get("date"))
            if not contract_code or not variety_code or base_date is None:
                continue

            for rank_num in RANK_BUCKETS:
                rows.append(
                    {
                        "R_ID": self.get_uuid(),
                        "REFERENCE_CODE": reference_code,
                        "REFERENCE_NAME": contract_code,
                        "BASEDATE": base_date,
                        "CREATEDATE": self.get_current_datetime(),
                        "CREATEUSER": "system",
                        "UPDATEDATE": self.get_current_datetime(),
                        "UPDATEUSER": "system",
                        "VARIETY_CODE": contract_code,
                        "VARIETY_NAME": variety_code,
                        "RANK_TYPE": f"top{rank_num}",
                        "RANK_NUM": rank_num,
                        "TOTAL_VOL": self._coerce_int(source_row.get(f"vol_top{rank_num}")),
                        "TOTAL_LONG_POSITION": self._coerce_int(
                            source_row.get(f"long_open_interest_top{rank_num}")
                        ),
                        "TOTAL_SHORT_POSITION": self._coerce_int(
                            source_row.get(f"short_open_interest_top{rank_num}")
                        ),
                        "VOL_CHANGE": self._coerce_int(source_row.get(f"vol_chg_top{rank_num}")),
                        "LONG_POSITION_CHANGE": self._coerce_int(
                            source_row.get(f"long_open_interest_chg_top{rank_num}")
                        ),
                        "SHORT_POSITION_CHANGE": self._coerce_int(
                            source_row.get(f"short_open_interest_chg_top{rank_num}")
                        ),
                    }
                )

        columns = [
            "R_ID",
            "REFERENCE_CODE",
            "REFERENCE_NAME",
            "BASEDATE",
            "CREATEDATE",
            "CREATEUSER",
            "UPDATEDATE",
            "UPDATEUSER",
            "VARIETY_CODE",
            "VARIETY_NAME",
            "RANK_TYPE",
            "RANK_NUM",
            "TOTAL_VOL",
            "TOTAL_LONG_POSITION",
            "TOTAL_SHORT_POSITION",
            "VOL_CHANGE",
            "LONG_POSITION_CHANGE",
            "SHORT_POSITION_CHANGE",
        ]
        return pd.DataFrame(rows, columns=columns)

    def run(self, symbols=None, max_symbols=None, lookback_days=None, sleep_seconds=0.5):
        """
        更新期货会员持仓排名汇总表数据
        从akshare获取数据并保存到FUTURES_RANK_SUM_DAILY表
        """
        self.logger.info("正在获取期货每日排名数据")
        table_name = "FUTURES_RANK_SUM_DAILY"
        using_default_symbols = symbols is None
        if symbols is None:
            symbol_list = self._normalize_symbol_list(self.get_future_symbol_list())
            if not symbol_list:
                symbol_list = DEFAULT_SYMBOLS.copy()
        else:
            symbol_list = self._normalize_symbol_list(symbols)

        max_symbols = int(max_symbols) if max_symbols is not None else None
        lookback_days = int(lookback_days) if lookback_days is not None else None
        if using_default_symbols and max_symbols is None:
            max_symbols = DEFAULT_MAX_SYMBOLS
        if using_default_symbols and lookback_days is None:
            lookback_days = DEFAULT_LOOKBACK_DAYS
        sleep_seconds = float(sleep_seconds or 0)
        if max_symbols is not None and len(symbol_list) > max_symbols:
            symbol_list = symbol_list[:max_symbols]
            self.logger.info(f"限制处理期货品种数量为{max_symbols}个")

        total_rows = 0
        for symbol in symbol_list:
            try:
                # 获取该品种最新数据日期
                begin_date = self.get_latest_date(
                    table_name, "BASEDATE", conditions={"REFERENCE_CODE": symbol}
                )
                if begin_date is None:
                    begin_date = "20000101"  # 默认开始日期
                    self.logger.info(f"{symbol}: 无历史数据，从{begin_date}开始获取")
                else:
                    # 将日期格式从YYYY-MM-DD转换为YYYYMMDD
                    begin_date = begin_date.replace("-", "")
                    self.logger.info(f"{symbol}: 最新数据日期 {begin_date}")
                if lookback_days is not None:
                    lookback_start = self._lookback_start(self.get_current_date(), lookback_days)
                    if begin_date < lookback_start:
                        begin_date = lookback_start
                        self.logger.info(f"{symbol}: 限制为最近{lookback_days}天")

                # 获取当前日期，格式为YYYYMMDD
                now_date = self.get_current_date().replace("-", "")

                if begin_date >= now_date:
                    self.logger.info(f"{symbol}: 数据已是最新，跳过")
                    continue

                self.logger.info(f"{symbol}: 获取数据 {begin_date} 至 {now_date}")

                # 从akshare获取数据
                kwargs = {
                    "start_day": begin_date,
                    "end_day": now_date,
                    "vars_list": [symbol.upper()],
                }
                df = self.fetch_ak_data("get_rank_sum_daily", **kwargs)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                if df is not None and not df.empty:
                    self.logger.info(f"{symbol}: 成功获取 {len(df)} 条数据")
                    df = self._transform_rank_sum_dataframe(df, reference_code=symbol)
                    if df.empty:
                        self.logger.warning(f"{symbol}: 转换后无可保存数据")
                        continue
                    # 保存数据到数据库
                    self.save_data(
                        df=df,
                        table_name=table_name,
                        on_duplicate_update=True,
                        unique_keys=["BASEDATE", "VARIETY_CODE", "RANK_TYPE"],
                    )

                    self.logger.info(f"{symbol}: 成功保存 {len(df)} 条数据到 {table_name}")
                    total_rows += len(df)
                else:
                    self.logger.warning(f"{symbol}: 未获取到数据")

            except Exception as e:
                self.logger.error(f"{symbol}: 处理失败 - {str(e)}", exc_info=True)
        return total_rows


if __name__ == "__main__":
    data_updater = FuturesRankSumDaily()
    data_updater.run()
