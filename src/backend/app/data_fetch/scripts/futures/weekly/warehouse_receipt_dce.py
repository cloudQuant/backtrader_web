from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDceWarehouseReceipt(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DCE_WAREHOUSE_RECEIPT"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DCE_WAREHOUSE_RECEIPT` (
                                      `R_ID` varchar(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` varchar(20) DEFAULT NULL COMMENT '数据来源代码',
                                      `REFERENCE_NAME` varchar(100) DEFAULT NULL COMMENT '数据来源名称',
                                      `BASEDATE` date NOT NULL COMMENT '数据日期',
                                      `PRODUCT_CODE` varchar(20) NOT NULL COMMENT '品种代码',
                                      `WAREHOUSE_ID` varchar(50) DEFAULT NULL COMMENT '仓库/分库ID',
                                      `WAREHOUSE_NAME` varchar(100) NOT NULL COMMENT '仓库/分库名称',
                                      `PREVIOUS_VOLUME` int DEFAULT NULL COMMENT '昨日仓单量',
                                      `CURRENT_VOLUME` int DEFAULT NULL COMMENT '今日仓单量',
                                      `DAILY_CHANGE` int DEFAULT NULL COMMENT '仓单增减',
                                      `IS_SUBTOTAL` tinyint(1) DEFAULT '0' COMMENT '是否小计行',
                                      `CREATEDATE` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` varchar(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` varchar(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      KEY `idx_basedate` (`BASEDATE`),
                                      KEY `idx_product_code` (`PRODUCT_CODE`),
                                      KEY `idx_warehouse_name` (`WAREHOUSE_NAME`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='大商所仓单日报';
                                """

    def run(self, start_date=None, end_date=None):
        """
        更新大连商品交易所仓单日报数据

        Args:
            start_date (str, optional): 开始日期，格式为'YYYYMMDD'，如果为None则从数据库最新日期或最早可用日期开始
            end_date (str, optional): 结束日期，格式为'YYYYMMDD'，如果为None则为当前日期前一天
        """
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取大连商品交易所仓单日报数据")
        table_name = "FUTURES_DCE_WAREHOUSE_RECEIPT"

        try:
            # 1. Date Handling
            if end_date is None:
                end_date = self.get_previous_date().replace("-", "")

            if start_date is None:
                latest_date = self.get_latest_date(self.table_name)
                start_date = end_date if latest_date is None else latest_date
            if "-" in start_date:
                start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            else:
                start_date_dt = datetime.strptime(start_date, "%Y%m%d").date()
            if "-" in end_date:
                end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            else:
                end_date_dt = datetime.strptime(end_date, "%Y%m%d").date()

            if start_date_dt > end_date_dt:
                self.logger.info(f"开始日期 {start_date} 不能晚于结束日期 {end_date}")
                return pd.DataFrame()

            trading_days = self.get_trading_day_list(
                start_date_dt.strftime("%Y-%m-%d"), end_date_dt.strftime("%Y-%m-%d")
            )

            if not trading_days:
                self.logger.info("在指定范围内没有需要更新的交易日")
                return pd.DataFrame()

            self.logger.info(
                f"准备更新从 {trading_days[0]} 到 {trading_days[-1]} 的仓单数据，共 {len(trading_days)} 个交易日"
            )

            all_dfs = []
            success_count = 0
            failed_dates = []

            # 2. Data Fetching and Processing Loop
            for date_str in trading_days:
                try:
                    date_yyyymmdd = date_str.replace("-", "")
                    self.logger.info(f"正在获取 {date_str} 的仓单日报数据")

                    # Fetch data
                    # data = ak.futures_dce_warehouse_receipt(date=date_yyyymmdd)
                    data = self.fetch_ak_data("futures_dce_warehouse_receipt", date_yyyymmdd)

                    if not data:
                        self.logger.warning(f"未获取到 {date_str} 的仓单日报数据")
                        continue

                    date_df_list = []

                    # Process each product's DataFrame
                    for product_name, df in data.items():
                        if df is None or df.empty:
                            continue

                        temp_df = df.copy()

                        # 获取原始列名用于调试
                        self.logger.info(f"原始列名: {list(temp_df.columns)}")

                        # 定义列名映射字典
                        column_mapping = {
                            "仓库/分库": "WAREHOUSE_NAME",
                            "昨日仓单量": "PREVIOUS_VOLUME",
                            "今日仓单量": "CURRENT_VOLUME",
                            "增减": "DAILY_CHANGE",
                            "可选提货地点/分库-数量": "DELIVERY_POINT_INFO",
                        }

                        # 重命名列
                        temp_df.rename(column_mapping, axis="columns", inplace=True)

                        # 输出映射后的列名
                        self.logger.info(f"映射后的列名: {list(temp_df.columns)}")

                        # Add Product Code
                        temp_df["PRODUCT_CODE"] = product_name

                        # Handle Subtotals
                        temp_df["IS_SUBTOTAL"] = (
                            temp_df["WAREHOUSE_NAME"].str.contains("小计").astype(int)
                        )

                        # Clean numeric columns
                        numeric_cols = [
                            "PREVIOUS_VOLUME",
                            "CURRENT_VOLUME",
                            "DAILY_CHANGE",
                        ]
                        for col in numeric_cols:
                            if col in temp_df.columns:
                                temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce").fillna(
                                    0
                                )

                        # Add system columns
                        temp_df["R_ID"] = [self.get_uuid() for _ in range(len(temp_df))]
                        temp_df["REFERENCE_CODE"] = "DCE_WAREHOUSE"
                        temp_df["REFERENCE_NAME"] = "大连商品交易所仓单日报"
                        temp_df["BASEDATE"] = datetime.strptime(date_str, "%Y-%m-%d").date()

                        # 只保留有效的列，确保没有中文列名或特殊字符列名
                        valid_columns = [
                            "WAREHOUSE_NAME",
                            "PREVIOUS_VOLUME",
                            "CURRENT_VOLUME",
                            "DAILY_CHANGE",
                            "PRODUCT_CODE",
                            "IS_SUBTOTAL",
                            "R_ID",
                            "REFERENCE_CODE",
                            "REFERENCE_NAME",
                            "BASEDATE",
                        ]

                        # 删除不需要的列，包括中文列和特殊字符列
                        temp_df = temp_df[valid_columns]

                        date_df_list.append(temp_df)

                    if date_df_list:
                        daily_df = pd.concat(date_df_list, ignore_index=True)

                        # Ensure all required columns exist
                        required_columns = [
                            "R_ID",
                            "REFERENCE_CODE",
                            "REFERENCE_NAME",
                            "BASEDATE",
                            "PRODUCT_CODE",
                            "WAREHOUSE_ID",
                            "WAREHOUSE_NAME",
                            "PREVIOUS_VOLUME",
                            "CURRENT_VOLUME",
                            "DAILY_CHANGE",
                            "IS_SUBTOTAL",
                            "CREATEDATE",
                            "CREATEUSER",
                            "UPDATEDATE",
                            "UPDATEUSER",
                        ]

                        for col in required_columns:
                            if col not in daily_df.columns:
                                daily_df[col] = None

                        # Add missing system columns
                        daily_df["CREATEDATE"] = self.get_current_datetime()
                        daily_df["CREATEUSER"] = "system"
                        daily_df["UPDATEDATE"] = self.get_current_datetime()
                        daily_df["UPDATEUSER"] = "system"

                        # 确保只保存有效的数据库列，过滤掉任何未映射的或不需要的列
                        valid_db_columns = [
                            "R_ID",
                            "REFERENCE_CODE",
                            "REFERENCE_NAME",
                            "BASEDATE",
                            "PRODUCT_CODE",
                            "WAREHOUSE_ID",
                            "WAREHOUSE_NAME",
                            "PREVIOUS_VOLUME",
                            "CURRENT_VOLUME",
                            "DAILY_CHANGE",
                            "IS_SUBTOTAL",
                            "CREATEDATE",
                            "CREATEUSER",
                            "UPDATEDATE",
                            "UPDATEUSER",
                        ]

                        # 只保留数据库表中定义的列
                        for col in daily_df.columns:
                            if col not in valid_db_columns:
                                daily_df = daily_df.drop(columns=[col], errors="ignore")
                                self.logger.info(f"删除了不在数据库表定义中的列: {col}")

                        # 转换数值列为整数类型
                        numeric_cols = [
                            "PREVIOUS_VOLUME",
                            "CURRENT_VOLUME",
                            "DAILY_CHANGE",
                        ]
                        for col in numeric_cols:
                            if col in daily_df.columns:
                                daily_df[col] = (
                                    pd.to_numeric(daily_df[col], errors="coerce")
                                    .fillna(0)
                                    .astype(int)
                                )

                        # 保存到数据库
                        self.logger.info(f"最终保存的列: {list(daily_df.columns)}")
                        self.save_data(daily_df, table_name)
                        success_count += 1
                        self.logger.info(
                            f"成功保存 {date_str} 的仓单日报数据，共 {len(daily_df)} 条记录"
                        )
                        all_dfs.append(daily_df)

                except Exception as e:
                    self.logger.error(f"处理 {date_str} 数据时出错: {str(e)}")
                    failed_dates.append(date_str)
                    continue

            # 3. Summary
            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个交易日的仓单数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何数据")
                final_df = pd.DataFrame()

            if failed_dates:
                self.logger.warning(f"以下日期的数据处理失败: {', '.join(failed_dates)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新大商所仓单日报数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesDceWarehouseReceipt()
    data_updater.run()
