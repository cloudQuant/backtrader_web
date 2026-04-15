from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesCzceWarehouseReceipt(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CZCE_WAREHOUSE_RECEIPT"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_CZCE_WAREHOUSE_RECEIPT (
                                    R_ID VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                                    REFERENCE_CODE VARCHAR(50) COMMENT '数据来源编码',
                                    REFERENCE_NAME VARCHAR(100) COMMENT '数据来源名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据日期',
                                    PRODUCT_CODE VARCHAR(20) NOT NULL COMMENT '品种代码',
                                    WAREHOUSE_ID VARCHAR(20) COMMENT '仓库编号',
                                    WAREHOUSE_NAME VARCHAR(100) COMMENT '仓库简称',
                                    CROP_YEAR VARCHAR(10) COMMENT '年度',
                                    GRADE VARCHAR(20) COMMENT '等级',
                                    BRAND VARCHAR(100) COMMENT '品牌',
                                    PRODUCTION_AREA VARCHAR(100) COMMENT '产地',
                                    RECEIPT_VOLUME INT COMMENT '仓单数量',
                                    DAILY_CHANGE INT COMMENT '当日增减',
                                    EFFECTIVE_FORECAST INT COMMENT '有效预报',
                                    PREMIUM_DISCOUNT INT COMMENT '升贴水',
                                    IS_SUBTOTAL TINYINT(1) DEFAULT 0 COMMENT '是否小计行',
                                    IS_TOTAL TINYINT(1) DEFAULT 0 COMMENT '是否总计行',
                                    -- 系统字段
                                    CREATEDATE DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                                    UPDATEDATE DATETIME COMMENT '更新时间',
                                    UPDATEUSER VARCHAR(50) COMMENT '更新用户',

                                    -- 主键约束
                                    PRIMARY KEY (R_ID),

                                    -- 索引
                                    INDEX IDX_CZCE_RECEIPT_DATE (BASEDATE),
                                    INDEX IDX_CZCE_RECEIPT_PRODUCT (PRODUCT_CODE),
                                    INDEX IDX_CZCE_RECEIPT_WAREHOUSE (WAREHOUSE_ID)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='郑州商品交易所仓单日报';
                                """

    def run(self, start_date=None, end_date=None):
        """
        更新郑州商品交易所仓单日报数据

        Args:
            start_date (str, optional): 开始日期，格式为'YYYYMMDD'，如果为None则从数据库最新日期或最早可用日期开始
            end_date (str, optional): 结束日期，格式为'YYYYMMDD'，如果为None则为当前日期前一天
        """
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        try:
            # 连接数据库
            self.connect_db()

            # 获取当前日期前一天作为默认结束日期
            if end_date is None:
                end_date = self.get_previous_date().replace("-", "")
            else:
                # 确保日期格式正确
                datetime.strptime(end_date, "%Y%m%d")

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
                self.logger.info(f"数据已是最新，无需更新。最新日期: {end_date_dt}")
                return pd.DataFrame()

            # 获取开始日期到结束日期之间的所有交易日
            trading_days = self.get_trading_day_list(
                start_date_dt.strftime("%Y-%m-%d"), end_date_dt.strftime("%Y-%m-%d")
            )

            if not trading_days:
                self.logger.info("没有需要更新的交易日")
                return pd.DataFrame()

            self.logger.info(
                f"准备更新从 {trading_days[0]} 到 {trading_days[-1]} 的仓单数据，共 {len(trading_days)} 个交易日"
            )

            all_dfs = []
            success_count = 0
            failed_dates = []

            for date_str in trading_days:
                try:
                    # 将日期格式从 YYYY-MM-DD 转换为 YYYYMMDD
                    date_yyyymmdd = date_str.replace("-", "")

                    self.logger.info(f"正在获取 {date_str} 仓单日报数据")

                    # 获取数据
                    # data = ak.futures_czce_warehouse_receipt(date=date_yyyymmdd)
                    data = self.fetch_ak_data("futures_czce_warehouse_receipt", date_yyyymmdd)

                    if not data:
                        self.logger.warning(f"未获取到 {date_str} 仓单日报数据")
                        continue

                    date_df = []

                    # 处理每个品种的数据
                    for product_code, df in data.items():
                        if df is None or df.empty:
                            continue

                        # 简化处理方法，跳过无法匹配的数据结构
                        # print(f"Processing {product_code} data with {len(df.columns)} columns")

                        # 尝试直接根据中文列名映射到英文列名
                        column_mapping = {}

                        # 定义常见的列名映射 - 使用更全面的映射策略
                        warehouse_id_columns = [
                            "仓库编号",
                            "机构编号",
                            "厂库编号",
                            "仓库/厂库编号",
                        ]
                        for col in warehouse_id_columns:
                            if col in df.columns:
                                column_mapping[col] = "WAREHOUSE_ID"
                                break

                        warehouse_name_columns = [
                            "仓库简称",
                            "机构简称",
                            "厂库简称",
                            "仓库/厂库",
                            "仓库/厂库简称",
                        ]
                        for col in warehouse_name_columns:
                            if col in df.columns:
                                column_mapping[col] = "WAREHOUSE_NAME"
                                break

                        if "年度" in df.columns:
                            column_mapping["年度"] = "CROP_YEAR"

                        if "等级" in df.columns:
                            column_mapping["等级"] = "GRADE"

                        if "品牌" in df.columns:
                            column_mapping["品牌"] = "BRAND"

                        if "产地" in df.columns:
                            column_mapping["产地"] = "PRODUCTION_AREA"
                        elif "提货地点" in df.columns:
                            column_mapping["提货地点"] = "PRODUCTION_AREA"
                        elif "提货点" in df.columns:
                            column_mapping["提货点"] = "PRODUCTION_AREA"

                        if "仓单数量" in df.columns:
                            column_mapping["仓单数量"] = "RECEIPT_VOLUME"
                        elif "确认书数量" in df.columns:
                            column_mapping["确认书数量"] = "RECEIPT_VOLUME"

                        if "当日增减" in df.columns:
                            column_mapping["当日增减"] = "DAILY_CHANGE"

                        if "有效预报" in df.columns:
                            column_mapping["有效预报"] = "EFFECTIVE_FORECAST"
                        elif "有效入库预报" in df.columns:
                            column_mapping["有效入库预报"] = "EFFECTIVE_FORECAST"

                        if "升贴水" in df.columns:
                            column_mapping["升贴水"] = "PREMIUM_DISCOUNT"

                        # 记录所有列，用于调试
                        self.logger.debug(f"原始列: {list(df.columns)}")

                        # 重命名列
                        df = df.rename(columns=column_mapping)

                        # 记录映射后的列，用于调试
                        self.logger.debug(f"映射后列: {list(df.columns)}")

                        # 如果缺失关键列，添加空列
                        for key_col in [
                            "WAREHOUSE_ID",
                            "WAREHOUSE_NAME",
                            "RECEIPT_VOLUME",
                            "DAILY_CHANGE",
                        ]:
                            if key_col not in df.columns:
                                df[key_col] = None

                        # Clean numeric columns
                        numeric_cols = [
                            "RECEIPT_VOLUME",
                            "DAILY_CHANGE",
                            "EFFECTIVE_FORECAST",
                            "PREMIUM_DISCOUNT",
                        ]
                        for col in numeric_cols:
                            if col in df.columns:
                                df[col] = (
                                    pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
                                )

                        # 添加品种代码和日期
                        df = df.copy()
                        df["PRODUCT_CODE"] = product_code
                        df["BASEDATE"] = datetime.strptime(date_str, "%Y-%m-%d").date()

                        # 处理小计和总计行
                        is_subtotal = pd.Series([False] * len(df), index=df.index)
                        is_total = pd.Series([False] * len(df), index=df.index)

                        if "WAREHOUSE_ID" in df.columns:
                            is_subtotal = is_subtotal | (df["WAREHOUSE_ID"].astype(str) == "小计")
                            is_total = is_total | (df["WAREHOUSE_ID"].astype(str) == "总计")

                        if "WAREHOUSE_NAME" in df.columns:
                            is_subtotal = is_subtotal | (df["WAREHOUSE_NAME"].astype(str) == "小计")
                            is_total = is_total | (df["WAREHOUSE_NAME"].astype(str) == "总计")

                        df["IS_SUBTOTAL"] = is_subtotal.astype(int)
                        df["IS_TOTAL"] = is_total.astype(int)

                        # 添加系统字段
                        df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                        df["REFERENCE_CODE"] = "CZCE_WAREHOUSE_RECEIPT"
                        df["REFERENCE_NAME"] = "郑州商品交易所仓单日报"
                        df["CREATEDATE"] = self.get_current_datetime()
                        df["CREATEUSER"] = "system"
                        df["UPDATEDATE"] = self.get_current_datetime()
                        df["UPDATEUSER"] = "system"

                        # 只保留已映射的英文列和必要的系统字段
                        valid_columns = list(column_mapping.values()) + [
                            "PRODUCT_CODE",
                            "BASEDATE",
                            "IS_SUBTOTAL",
                            "IS_TOTAL",
                            "R_ID",
                            "REFERENCE_CODE",
                            "REFERENCE_NAME",
                            "CREATEDATE",
                            "CREATEUSER",
                            "UPDATEDATE",
                            "UPDATEUSER",
                        ]

                        # 只保留映射后的英文列名和必要的系统字段
                        df = df[valid_columns]
                        date_df.append(df)

                    if date_df:
                        # 合并当天所有品种的数据
                        daily_df = pd.concat(date_df, ignore_index=True)

                        # 确保所有必需的列都存在
                        required_columns = [
                            "WAREHOUSE_ID",
                            "WAREHOUSE_NAME",
                            "PRODUCT_CODE",
                            "BASEDATE",
                            "IS_SUBTOTAL",
                            "IS_TOTAL",
                            "R_ID",
                            "REFERENCE_CODE",
                            "REFERENCE_NAME",
                            "CREATEDATE",
                            "CREATEUSER",
                            "UPDATEDATE",
                            "UPDATEUSER",
                            "RECEIPT_VOLUME",
                            "DAILY_CHANGE",
                        ]

                        for col in required_columns:
                            if col not in daily_df.columns:
                                daily_df[col] = None

                        # 保存到数据库
                        try:
                            self.save_data(daily_df, "FUTURES_CZCE_WAREHOUSE_RECEIPT")
                            success_count += 1
                            self.logger.info(
                                f"成功保存 {date_str} 的仓单日报数据，共 {len(daily_df)} 条记录"
                            )
                            all_dfs.append(daily_df)
                        except Exception as e:
                            self.logger.error(f"保存 {date_str} 数据失败: {str(e)}")
                            failed_dates.append(date_str)

                except Exception as e:
                    self.logger.error(f"处理 {date_str} 数据时出错: {str(e)}")
                    failed_dates.append(date_str)
                    continue

            # 输出汇总信息
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
            self.logger.error(f"更新仓单日报数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesCzceWarehouseReceipt()
    data_updater.run()
