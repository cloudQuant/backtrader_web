import re
import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesMemberPositionRank(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_MEMBER_POSITION_RANK"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_MEMBER_POSITION_RANK (
                                        R_ID VARCHAR(36) NOT NULL COMMENT 'UUID生成的唯一标识',
                                        REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据的名称代码',
                                        REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据的中文名称',
                                        BASEDATE DATE NOT NULL COMMENT '数据的日期',
                                        CREATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建日期',
                                        CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                        UPDATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日期',
                                        UPDATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                        -- 业务字段
                                        EXCHANGE_CODE VARCHAR(10) NOT NULL COMMENT '交易所代码(DCE/CZCE/SHFE/GFEX/CFFEX)',
                                        EXCHANGE_NAME VARCHAR(50) NOT NULL COMMENT '交易所名称',
                                        SYMBOL VARCHAR(20) NOT NULL COMMENT '具体合约代码',
                                        VARIETY VARCHAR(10) NOT NULL COMMENT '品种代码',
                                        RANK_NUM INT NOT NULL COMMENT '排名',

                                        -- 成交量相关
                                        VOL_PARTY_NAME VARCHAR(100) COMMENT '成交量排名会员简称',
                                        VOL BIGINT COMMENT '成交量',
                                        VOL_CHG BIGINT COMMENT '成交量增减',

                                        -- 多头持仓相关
                                        LONG_PARTY_NAME VARCHAR(100) COMMENT '多头持仓排名会员简称',
                                        LONG_OPEN_INTEREST BIGINT COMMENT '持买单量',
                                        LONG_OPEN_INTEREST_CHG BIGINT COMMENT '持买单量增减',

                                        -- 空头持仓相关
                                        SHORT_PARTY_NAME VARCHAR(100) COMMENT '空头持仓排名会员简称',
                                        SHORT_OPEN_INTEREST BIGINT COMMENT '持卖单量',
                                        SHORT_OPEN_INTEREST_CHG BIGINT COMMENT '持卖单量增减',

                                        PRIMARY KEY (R_ID),
                                        KEY idx_basedate (BASEDATE),
                                        KEY idx_symbol (SYMBOL),
                                        KEY idx_exchange (EXCHANGE_CODE),
                                        KEY idx_variety (VARIETY)
                                        # UNIQUE KEY uk_position_rank (BASEDATE, EXCHANGE_CODE, SYMBOL, RANK_NUM)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='期货会员持仓排名表';
                                """

    def clean_numeric_columns(
        self,
        df: pd.DataFrame,
        cols: list,
        decimal_separator: str = ".",
        thousand_separator: str = ",",
    ) -> pd.DataFrame:
        """
        清理包含千分位符的数值列

        Args:
            df: 原始数据框
            cols: 需要处理的列名列表
            decimal_separator: 小数点分隔符（默认点号）
            thousand_separator: 千分位分隔符（默认逗号）

        Returns:
            清洗后的数据框
        """
        try:
            # 创建正则表达式模式（保留数字、小数点、负号）
            pattern = f"[^0-9{re.escape(decimal_separator)}{re.escape(thousand_separator)}-]"

            for col in cols:
                # 转换为字符串类型
                df[col] = df[col].astype(str)

                # 清除非数字字符（保留小数点和千分位符）
                df[col] = df[col].str.replace(pattern, "", regex=True)

                # 处理千分位符和小数点冲突（如1,234.56→1234.56）
                if thousand_separator != ".":
                    df[col] = df[col].str.replace(thousand_separator, "", regex=False)

                # 转换为数值类型
                df[col] = pd.to_numeric(df[col], errors="coerce")

                # 验证转换结果
                invalid = df[col].isna()
                if invalid.any():
                    # print(f"警告: 列 {col} 存在无效数据（共{invalid.sum()}条）")
                    # 可选择填充或标记无效值
                    # df[col] = df[col].fillna(0).astype(int)
                    pass

            return df

        except Exception:
            # print(f"数据清洗失败: {str(e)}")
            return df

    def _update_czce_rank_table(self, begin_date):
        now_date = self.get_previous_date()
        if begin_date is None:
            begin_date = "2015-10-08"
        if begin_date >= now_date:
            return
        trading_day_list = self.get_trading_day_list(start_date=begin_date, end_date=now_date)
        # print(trading_day_list)
        for trading_day in trading_day_list:
            self.logger.info(f"{trading_day} is running")
            new_trading_day = trading_day.replace("-", "")
            # if new_trading_day < "2015-10-08":
            #     continue
            # content = ak.get_czce_rank_table(date=new_trading_day)
            content = self.fetch_ak_data("get_rank_table_czce", new_trading_day)
            time.sleep(1)
            all_df_list = []
            for name, df in content.items():
                if df is not None and not df.empty:
                    df.columns = [
                        "RANK_NUM",
                        "VOL_PARTY_NAME",
                        "VOL",
                        "VOL_CHG",
                        "LONG_PARTY_NAME",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_PARTY_NAME",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                        "SYMBOL",
                        "VARIETY",
                    ]
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = name
                    df["REFERENCE_NAME"] = name
                    df["BASEDATE"] = trading_day
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df["EXCHANGE_CODE"] = "CZCE"
                    df["EXCHANGE_NAME"] = "郑商所"
                    col_list = [
                        "RANK_NUM",
                        "VOL",
                        "VOL_CHG",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                    ]
                    df = self.clean_numeric_columns(df, col_list)
                    all_df_list.append(df)
                else:
                    self.logger.info(f"czce中{name}获取到的数据为空")
            if len(all_df_list) > 0:
                all_df = pd.concat(all_df_list, ignore_index=True)
                self.save_data(all_df, "FUTURES_MEMBER_POSITION_RANK", ignore_duplicates=True)
            else:
                self.logger.info(f"中金所中{trading_day} 获取到的数据为空")

    def _update_cffex_rank_table(self, begin_date):
        now_date = self.get_previous_date()
        if begin_date is None:
            begin_date = "2010-04-16"
        if begin_date >= now_date:
            return
        trading_day_list = self.get_trading_day_list(start_date=begin_date, end_date=now_date)
        # print(trading_day_list)
        for trading_day in trading_day_list:
            self.logger.info(f"{trading_day} is running")
            new_trading_day = trading_day.replace("-", "")
            if new_trading_day < "20100416":
                continue
            # content = ak.get_czce_rank_table(date=new_trading_day)
            content = self.fetch_ak_data("get_cffex_rank_table", new_trading_day)
            time.sleep(1)
            all_df_list = []
            for name, df in content.items():
                if df is not None and not df.empty:
                    df.columns = [
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "LONG_PARTY_NAME",
                        "RANK_NUM",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                        "SHORT_PARTY_NAME",
                        "SYMBOL",
                        "VOL",
                        "VOL_CHG",
                        "VOL_PARTY_NAME",
                        "VARIETY",
                    ]
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = name
                    df["REFERENCE_NAME"] = name
                    df["BASEDATE"] = trading_day
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df["EXCHANGE_CODE"] = "CFFEX"
                    df["EXCHANGE_NAME"] = "中金所"
                    col_list = [
                        "RANK_NUM",
                        "VOL",
                        "VOL_CHG",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                    ]
                    df = df.fillna(-999)
                    df = self.clean_numeric_columns(df, col_list)
                    all_df_list.append(df)
                else:
                    self.logger.info(f"中金所中{name}获取到的数据为空")
            if len(all_df_list) > 0:
                all_df = pd.concat(all_df_list, ignore_index=True)
                self.save_data(all_df, "FUTURES_MEMBER_POSITION_RANK", ignore_duplicates=True)
            else:
                self.logger.info(f"中金所中{trading_day} 获取到的数据为空")

    def _update_dce_rank_table(self, begin_date):
        now_date = self.get_previous_date()
        if begin_date is None:
            begin_date = "2010-01-04"
        if begin_date >= now_date:
            return
        trading_day_list = self.get_trading_day_list(start_date=begin_date, end_date=now_date)
        # print(trading_day_list)
        for trading_day in trading_day_list:
            self.logger.info(f"{trading_day} is running")
            # content = ak.futures_dce_position_rank(date=trading_day.replace("-", ""))
            content = self.fetch_ak_data("futures_dce_position_rank", trading_day)
            time.sleep(1)
            all_df_list = []
            for name, df in content.items():
                if df is not None and not df.empty:
                    df.columns = [
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "LONG_PARTY_NAME",
                        "RANK_NUM",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                        "SHORT_PARTY_NAME",
                        "VOL",
                        "VOL_CHG",
                        "VOL_PARTY_NAME",
                        "SYMBOL",
                        "VARIETY",
                    ]
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = name
                    df["REFERENCE_NAME"] = name
                    df["BASEDATE"] = trading_day
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df["EXCHANGE_CODE"] = "DCE"
                    df["EXCHANGE_NAME"] = "大商所"
                    col_list = [
                        "RANK_NUM",
                        "VOL",
                        "VOL_CHG",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                    ]
                    df = self.clean_numeric_columns(df, col_list)
                    all_df_list.append(df)
                    # self.save_data(df, "FUTURES_MEMBER_POSITION_RANK")
                else:
                    self.logger.info(f"大商所中{name}获取到的数据为空")
            if len(all_df_list) > 0:
                all_df = pd.concat(all_df_list, ignore_index=True)
                self.save_data(all_df, "FUTURES_MEMBER_POSITION_RANK", ignore_duplicates=True)
            else:
                self.logger.info(f"中金所中{trading_day} 获取到的数据为空")

    def _update_gfex_rank_table(self, begin_date):
        now_date = self.get_previous_date()
        if begin_date >= now_date:
            return
        trading_day_list = self.get_trading_day_list(start_date=begin_date, end_date=now_date)
        # print(trading_day_list)
        for trading_day in trading_day_list:
            self.logger.info(f"{trading_day} is running")
            new_trading_day = trading_day.replace("-", "")
            if new_trading_day < "20231110":
                continue
            # content = ak.futures_dce_position_rank(date=new_trading_day)
            content = self.fetch_ak_data("futures_gfex_position_rank", new_trading_day)
            time.sleep(1)
            all_df_list = []
            for name, df in content.items():
                if df is not None and not df.empty:
                    df.columns = [
                        "RANK_NUM",
                        "VOL_PARTY_NAME",
                        "VOL",
                        "VOL_CHG",
                        "LONG_PARTY_NAME",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_PARTY_NAME",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                        "SYMBOL",
                        "VARIETY",
                    ]
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = name
                    df["REFERENCE_NAME"] = name
                    df["BASEDATE"] = trading_day
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df["EXCHANGE_CODE"] = "GFEX"
                    df["EXCHANGE_NAME"] = "广期所"
                    col_list = [
                        "RANK_NUM",
                        "VOL",
                        "VOL_CHG",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                    ]
                    df = self.clean_numeric_columns(df, col_list)
                    all_df_list.append(df)
                    # self.save_data(df, "FUTURES_MEMBER_POSITION_RANK")
            if len(all_df_list) > 0:
                all_df = pd.concat(all_df_list, ignore_index=True)
                self.save_data(all_df, "FUTURES_MEMBER_POSITION_RANK", ignore_duplicates=True)
            else:
                self.logger.info(f"中金所中{trading_day} 获取到的数据为空")

    def _update_shfe_rank_table(self, begin_date):
        now_date = self.get_previous_date()
        if begin_date is None:
            begin_date = "2002-01-07"
        if begin_date >= now_date:
            return
        trading_day_list = self.get_trading_day_list(start_date=begin_date, end_date=now_date)
        # print(trading_day_list)
        for trading_day in trading_day_list:
            self.logger.info(f"{trading_day} is running")
            new_trading_day = trading_day.replace("-", "")
            # content = ak.futures_dce_position_rank(date=new_trading_day)
            content = self.fetch_ak_data("get_shfe_rank_table", new_trading_day)
            time.sleep(1)
            for name, df in content.items():
                if df is not None and not df.empty:
                    df.columns = [
                        "SYMBOL",
                        "SHORT_PARTY_NAME",
                        "LONG_PARTY_NAME",
                        "RANK_NUM",
                        "VOL_PARTY_NAME",
                        "LONG_OPEN_INTEREST",
                        "VOL",
                        "VOL_CHG",
                        "SHORT_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "VARIETY",
                    ]
                    df["R_ID"] = [self.get_uuid() for i in range(len(df))]
                    df["REFERENCE_CODE"] = name
                    df["REFERENCE_NAME"] = name
                    df["BASEDATE"] = trading_day
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df["EXCHANGE_CODE"] = "GFEX"
                    df["EXCHANGE_NAME"] = "广期所"
                    col_list = [
                        "RANK_NUM",
                        "VOL",
                        "VOL_CHG",
                        "LONG_OPEN_INTEREST",
                        "LONG_OPEN_INTEREST_CHG",
                        "SHORT_OPEN_INTEREST",
                        "SHORT_OPEN_INTEREST_CHG",
                    ]
                    df = self.clean_numeric_columns(df, col_list)
                    self.save_data(df, "FUTURES_MEMBER_POSITION_RANK", ignore_duplicates=True)
                else:
                    self.logger.info(f"中金所中{name}获取到的数据为空")

    def run(self):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取期货会员持仓表数据")
        table_name = "FUTURES_MEMBER_POSITION_RANK"
        exchange_list = ["郑商所", "中金所", "大商所", "广期所", "上期所"]
        for exchange in exchange_list:
            begin_date = self.get_latest_date(
                table_name, "BASEDATE", conditions={"EXCHANGE_NAME": exchange}
            )
            if exchange == "郑商所":
                self._update_czce_rank_table(begin_date)
            if exchange == "广期货":
                self._update_gfex_rank_table(begin_date)
            if exchange == "大商所":
                self._update_dce_rank_table(begin_date)
            if exchange == "中金所":
                self._update_cffex_rank_table(begin_date)
            if exchange == "上期所":
                self._update_shfe_rank_table(begin_date)


if __name__ == "__main__":
    future_data_updater = FuturesMemberPositionRank()
    future_data_updater.run()
