import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDeliveryMatchDce(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DELIVERY_MATCH_DCE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DELIVERY_MATCH_DCE` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'DCE_DELIVERY_MATCH' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '大连商品交易所交割配对' COMMENT '参考名称',
                                  `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                  `MATCH_DATE` DATE NOT NULL COMMENT '配对日期',
                                  `BUYER_MEMBER_ID` VARCHAR(20) NOT NULL COMMENT '买会员号',
                                  `SELLER_MEMBER_ID` VARCHAR(20) NOT NULL COMMENT '卖会员号',
                                  `MATCHED_LOTS` INT DEFAULT 0 COMMENT '配对手数(手)',
                                  `DELIVERY_SETTLEMENT_PRICE` DECIMAL(18, 2) COMMENT '交割结算价(元/吨)',
                                  `PRODUCT_CATEGORY` VARCHAR(10) COMMENT '品种代码',
                                  `UNIT` VARCHAR(20) COMMENT '价格单位',
                                  `CURRENCY` VARCHAR(3) DEFAULT 'CNY' COMMENT '币种',
                                  `IS_NON_FUTURES_COMPANY` TINYINT(1) DEFAULT 0 COMMENT '是否非期货公司会员(1:是,0:否)',
                                  `CREATEDATE` DATETIME COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                  PRIMARY KEY (`R_ID`),
                                  -- UNIQUE KEY `IDX_DCE_DELIVERY_MATCH_UNIQUE` (`CONTRACT_CODE`, `MATCH_DATE`, `BUYER_MEMBER_ID`, `SELLER_MEMBER_ID`, `DELIVERY_SETTLEMENT_PRICE`),
                                  KEY `IDX_DCE_DELIVERY_MATCH_CONTRACT` (`CONTRACT_CODE`),
                                  KEY `IDX_DCE_DELIVERY_MATCH_DATE` (`MATCH_DATE`),
                                  KEY `IDX_DCE_DELIVERY_MATCH_BUYER` (`BUYER_MEMBER_ID`),
                                  KEY `IDX_DCE_DELIVERY_MATCH_SELLER` (`SELLER_MEMBER_ID`),
                                  KEY `IDX_DCE_DELIVERY_MATCH_PRODUCT` (`PRODUCT_CATEGORY`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大连商品交易所交割配对表';

                                """

    def run(self):
        """
        更新大连商品交易所交割配对数据。

        :param start_date: 开始日期，格式为'YYYY-MM-DD'，如果为None则从数据库最新日期或最早可用日期开始
        :param end_date: 结束日期，格式为'YYYY-MM-DD'，如果为None则为当前日期前一天
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("正在获取大连商品交易所交割配对数据")
        table_name = "FUTURES_DELIVERY_MATCH_DCE"
        trading_rules_table = "FUTURES_TRADING_RULES"

        try:
            # 1. Get DCE symbols from FUTURES_TRADING_RULES
            self.connect_db()
            query = f"SELECT DISTINCT REFERENCE_NAME FROM {trading_rules_table} WHERE EXCHANGE = '大商所' AND REFERENCE_CODE NOT LIKE '%期权%'"  # nosec B608
            self.cursor.execute(query)
            dce_symbols = [row[0] for row in self.cursor.fetchall()]
            self.disconnect_db()

            if not dce_symbols:
                self.logger.warning("未找到大商所的期货品种，跳过数据获取。")
                return pd.DataFrame()

            self.logger.info(f"获取到大商所期货品种: {dce_symbols}")

            all_dfs = []
            success_count = 0
            failed_dates_symbols = []

            for symbol in dce_symbols:
                symbol = symbol.lower()
                self.logger.info(f"品种 {symbol}: 准备更新")
                try:
                    self.logger.info(f"正在获取 {symbol} 的交割配对数据")

                    # Fetch data
                    # df = ak.futures_delivery_match_dce(symbol=symbol)
                    df = self.fetch_ak_data("futures_delivery_match_dce", symbol)

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {symbol} 的交割配对数据")
                        continue

                    # Filter by date, as akshare might return data for other dates
                    df["配对日期"] = pd.to_datetime(df["配对日期"]).dt.strftime("%Y-%m-%d")
                    # df = df[df['配对日期'] == date_str]

                    if df.empty:
                        self.logger.info(f"未找到 {symbol} 的交割配对数据")
                        continue

                    # Rename columns
                    df.rename(
                        columns={
                            "合约号": "CONTRACT_CODE",
                            "配对日期": "MATCH_DATE",
                            "买会员号": "BUYER_MEMBER_ID",
                            "卖会员号": "SELLER_MEMBER_ID",
                            "配对手数": "MATCHED_LOTS",
                            "交割结算价": "DELIVERY_SETTLEMENT_PRICE",
                        },
                        inplace=True,
                    )

                    # Add system columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "DCE_DELIVERY_MATCH"
                    df["REFERENCE_NAME"] = "大连商品交易所交割配对"
                    df["PRODUCT_CATEGORY"] = symbol  # Use the input symbol as product category
                    df["UNIT"] = self.contract_units.get(
                        symbol.lower(), "未知"
                    )  # Get unit from mapping
                    df["CURRENCY"] = "CNY"
                    df["BUYER_MEMBER_ID"] = df["BUYER_MEMBER_ID"].astype(str)
                    df["SELLER_MEMBER_ID"] = df["SELLER_MEMBER_ID"].astype(str)
                    # Determine IS_NON_FUTURES_COMPANY
                    df["IS_NON_FUTURES_COMPANY"] = 0
                    df.loc[
                        df["BUYER_MEMBER_ID"].str.contains(r"\*", na=False)
                        | df["SELLER_MEMBER_ID"].str.contains(r"\*", na=False),
                        "IS_NON_FUTURES_COMPANY",
                    ] = 1

                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"

                    # Convert data types
                    df["MATCHED_LOTS"] = (
                        pd.to_numeric(df["MATCHED_LOTS"], errors="coerce").fillna(0).astype(int)
                    )
                    df["DELIVERY_SETTLEMENT_PRICE"] = pd.to_numeric(
                        df["DELIVERY_SETTLEMENT_PRICE"], errors="coerce"
                    ).fillna(0.0)

                    # Ensure all required columns exist and are in the correct order (optional but good practice)
                    required_columns = [
                        "R_ID",
                        "REFERENCE_CODE",
                        "REFERENCE_NAME",
                        "CONTRACT_CODE",
                        "MATCH_DATE",
                        "BUYER_MEMBER_ID",
                        "SELLER_MEMBER_ID",
                        "MATCHED_LOTS",
                        "DELIVERY_SETTLEMENT_PRICE",
                        "PRODUCT_CATEGORY",
                        "UNIT",
                        "CURRENCY",
                        "IS_NON_FUTURES_COMPANY",
                        "CREATEDATE",
                        "CREATEUSER",
                        "UPDATEDATE",
                        "UPDATEUSER",
                    ]

                    for col in required_columns:
                        if col not in df.columns:
                            df[col] = None

                    # Reorder columns to match DDL (optional)
                    df = df[required_columns]
                    now_match_date = self.get_latest_date(
                        self.table_name,
                        "MATCH_DATE",
                        conditions={"PRODUCT_CATEGORY": symbol.lower()},
                    )
                    df = df[df["MATCH_DATE"] >= now_match_date]
                    # Save to database
                    self.save_data(df, table_name)
                    success_count += 1
                    self.logger.info(f"成功保存 {symbol} 的交割配对数据，共 {len(df)} 条记录")
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(f"处理 {symbol} 数据时出错，品种: {symbol}: {str(e)}")
                    failed_dates_symbols.append(f"{symbol}")
                    continue
                time.sleep(5)
            # 3. Summary
            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个交易日的交割配对数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何数据")
                final_df = pd.DataFrame()

            if failed_dates_symbols:
                self.logger.warning(f"以下品种的数据处理失败: {', '.join(failed_dates_symbols)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新大连商品交易所交割配对数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesDeliveryMatchDce()
    data_updater.run()
