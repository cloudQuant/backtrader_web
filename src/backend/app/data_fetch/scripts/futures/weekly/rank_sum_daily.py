import time

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesRankSumDaily(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_RANK_SUM_DAILY"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_RANK_SUM_DAILY (
                                    -- 系统字段
                                    R_ID VARCHAR(36) NOT NULL COMMENT 'UUID生成的唯一标识',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据的名称代码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据的中文名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据的日期',
                                    CREATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建日期',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                    UPDATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日期',
                                    UPDATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                    -- 业务字段
                                    SYMBOL VARCHAR(50) NOT NULL COMMENT '合约代码',
                                    VARIETY VARCHAR(20) NOT NULL COMMENT '品种代码',

                                    -- 前5名数据
                                    VOL_TOP5 BIGINT COMMENT '前5名成交量',
                                    VOL_CHG_TOP5 BIGINT COMMENT '前5名成交量变化',
                                    LONG_OPEN_INTEREST_TOP5 BIGINT COMMENT '前5名持买仓量',
                                    LONG_OPEN_INTEREST_CHG_TOP5 BIGINT COMMENT '前5名持买仓量变化',
                                    SHORT_OPEN_INTEREST_TOP5 BIGINT COMMENT '前5名持卖仓量',
                                    SHORT_OPEN_INTEREST_CHG_TOP5 BIGINT COMMENT '前5名持卖仓量变化',

                                    -- 前10名数据
                                    VOL_TOP10 BIGINT COMMENT '前10名成交量',
                                    VOL_CHG_TOP10 BIGINT COMMENT '前10名成交量变化',
                                    LONG_OPEN_INTEREST_TOP10 BIGINT COMMENT '前10名持买仓量',
                                    LONG_OPEN_INTEREST_CHG_TOP10 BIGINT COMMENT '前10名持买仓量变化',
                                    SHORT_OPEN_INTEREST_TOP10 BIGINT COMMENT '前10名持卖仓量',
                                    SHORT_OPEN_INTEREST_CHG_TOP10 BIGINT COMMENT '前10名持卖仓量变化',

                                    -- 前15名数据
                                    VOL_TOP15 BIGINT COMMENT '前15名成交量',
                                    VOL_CHG_TOP15 BIGINT COMMENT '前15名成交量变化',
                                    LONG_OPEN_INTEREST_TOP15 BIGINT COMMENT '前15名持买仓量',
                                    LONG_OPEN_INTEREST_CHG_TOP15 BIGINT COMMENT '前15名持买仓量变化',
                                    SHORT_OPEN_INTEREST_TOP15 BIGINT COMMENT '前15名持卖仓量',
                                    SHORT_OPEN_INTEREST_CHG_TOP15 BIGINT COMMENT '前15名持卖仓量变化',

                                    -- 前20名数据
                                    VOL_TOP20 BIGINT COMMENT '前20名成交量',
                                    VOL_CHG_TOP20 BIGINT COMMENT '前20名成交量变化',
                                    LONG_OPEN_INTEREST_TOP20 BIGINT COMMENT '前20名持买仓量',
                                    LONG_OPEN_INTEREST_CHG_TOP20 BIGINT COMMENT '前20名持买仓量变化',
                                    SHORT_OPEN_INTEREST_TOP20 BIGINT COMMENT '前20名持卖仓量',
                                    SHORT_OPEN_INTEREST_CHG_TOP20 BIGINT COMMENT '前20名持卖仓量变化',

                                    PRIMARY KEY (R_ID),
                                    UNIQUE KEY UK_SYMBOL_DATE (SYMBOL, BASEDATE),
                                    KEY IDX_VARIETY (VARIETY),
                                    KEY IDX_BASEDATE (BASEDATE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='期货会员持仓排名汇总表';

                                """

    def run(self):
        """
        更新期货会员持仓排名汇总表数据
        从akshare获取数据并保存到FUTURES_RANK_SUM_DAILY表
        """
        self.logger.info("正在获取期货每日排名数据")
        table_name = "FUTURES_RANK_SUM_DAILY"
        symbol_list = self.get_future_symbol_list()

        for symbol in symbol_list:
            try:
                # 获取该品种最新数据日期
                begin_date = self.get_latest_date(
                    table_name, "BASEDATE", conditions={"SYMBOL": symbol}
                )
                if begin_date is None:
                    begin_date = "20000101"  # 默认开始日期
                    self.logger.info(f"{symbol}: 无历史数据，从{begin_date}开始获取")
                else:
                    # 将日期格式从YYYY-MM-DD转换为YYYYMMDD
                    begin_date = begin_date.replace("-", "")
                    self.logger.info(f"{symbol}: 最新数据日期 {begin_date}")

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
                time.sleep(5)
                if df is not None and not df.empty:
                    self.logger.info(f"{symbol}: 成功获取 {len(df)} 条数据")
                    col_list = [
                        "vol_top5",
                        "vol_chg_top5",
                        "long_open_interest_top5",
                        "long_open_interest_chg_top5",
                        "short_open_interest_top5",
                        "short_open_interest_chg_top5",
                        "vol_top10",
                        "vol_chg_top10",
                        "long_open_interest_top10",
                        "long_open_interest_chg_top10",
                        "short_open_interest_top10",
                        "short_open_interest_chg_top10",
                        "vol_top15",
                        "vol_chg_top15",
                        "long_open_interest_top15",
                        "long_open_interest_chg_top15",
                        "short_open_interest_top15",
                        "short_open_interest_chg_top15",
                        "vol_top20",
                        "vol_chg_top20",
                        "long_open_interest_top20",
                        "long_open_interest_chg_top20",
                        "short_open_interest_top20",
                        "short_open_interest_chg_top20",
                    ]
                    df[col_list] = df[col_list].astype("int")

                    # 重命名列以匹配数据库字段
                    # 中获取字段名,进行匹配，然后替换
                    df = df.rename(
                        columns={
                            "symbol": "SYMBOL",
                            "variety": "VARIETY",
                            "vol_top5": "VOL_TOP5",
                            "vol_chg_top5": "VOL_CHG_TOP5",
                            "long_open_interest_top5": "LONG_OPEN_INTEREST_TOP5",
                            "long_open_interest_chg_top5": "LONG_OPEN_INTEREST_CHG_TOP5",
                            "short_open_interest_top5": "SHORT_OPEN_INTEREST_TOP5",
                            "short_open_interest_chg_top5": "SHORT_OPEN_INTEREST_CHG_TOP5",
                            "vol_top10": "VOL_TOP10",
                            "vol_chg_top10": "VOL_CHG_TOP10",
                            "long_open_interest_top10": "LONG_OPEN_INTEREST_TOP10",
                            "long_open_interest_chg_top10": "LONG_OPEN_INTEREST_CHG_TOP10",
                            "short_open_interest_top10": "SHORT_OPEN_INTEREST_TOP10",
                            "short_open_interest_chg_top10": "SHORT_OPEN_INTEREST_CHG_TOP10",
                            "vol_top15": "VOL_TOP15",
                            "vol_chg_top15": "VOL_CHG_TOP15",
                            "long_open_interest_top15": "LONG_OPEN_INTEREST_TOP15",
                            "long_open_interest_chg_top15": "LONG_OPEN_INTEREST_CHG_TOP15",
                            "short_open_interest_top15": "SHORT_OPEN_INTEREST_TOP15",
                            "short_open_interest_chg_top15": "SHORT_OPEN_INTEREST_CHG_TOP15",
                            "vol_top20": "VOL_TOP20",
                            "vol_chg_top20": "VOL_CHG_TOP20",
                            "long_open_interest_top20": "LONG_OPEN_INTEREST_TOP20",
                            "long_open_interest_chg_top20": "LONG_OPEN_INTEREST_CHG_TOP20",
                            "short_open_interest_top20": "SHORT_OPEN_INTEREST_TOP20",
                            "short_open_interest_chg_top20": "SHORT_OPEN_INTEREST_CHG_TOP20",
                            "date": "BASEDATE",
                        }
                    )
                    # 添加系统字段
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = symbol
                    df["REFERENCE_NAME"] = symbol
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    # df = self.clean_numeric_columns(df, col_list)
                    # 保存数据到数据库
                    self.save_data(
                        df=df,
                        table_name=table_name,
                        on_duplicate_update=True,
                        unique_keys=["SYMBOL", "BASEDATE"],
                    )

                    self.logger.info(f"{symbol}: 成功保存 {len(df)} 条数据到 {table_name}")
                else:
                    self.logger.warning(f"{symbol}: 未获取到数据")

            except Exception as e:
                self.logger.error(f"{symbol}: 处理失败 - {str(e)}", exc_info=True)


if __name__ == "__main__":
    data_updater = FuturesRankSumDaily()
    data_updater.run()
