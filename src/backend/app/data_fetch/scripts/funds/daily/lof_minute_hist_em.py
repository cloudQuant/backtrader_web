import time
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class LofMinuteHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 统一的LOF分钟数据表
        self.table_name = "LOF_MINUTE_HIST_EM"

        # 统一表结构 (支持1分钟和5分钟数据)
        self.create_table_sql = r"""
                                CREATE TABLE `LOF_MINUTE_HIST_EM` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'LOF_MINUTE_HIST' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT 'LOF基金分时行情表(东方财富)' COMMENT '参考名称',

                                  -- 基础信息
                                  `LOF_CODE` VARCHAR(20) NOT NULL COMMENT 'LOF代码',
                                  `PERIOD` VARCHAR(10) NOT NULL COMMENT '周期(1/5/15/30/60分钟)',
                                  `ADJUST_TYPE` VARCHAR(10) DEFAULT '' COMMENT '复权类型(空:不复权,qfq:前复权,hfq:后复权)',

                                  -- 时间信息
                                  `TRADE_DATETIME` DATETIME NOT NULL COMMENT '交易时间',
                                  `TRADE_DATE` DATE GENERATED ALWAYS AS (DATE(TRADE_DATETIME)) STORED COMMENT '交易日期',

                                  -- 价格信息
                                  `OPEN_PRICE` DECIMAL(10, 4) COMMENT '开盘价',
                                  `CLOSE_PRICE` DECIMAL(10, 4) COMMENT '收盘价',
                                  `HIGH_PRICE` DECIMAL(10, 4) COMMENT '最高价',
                                  `LOW_PRICE` DECIMAL(10, 4) COMMENT '最低价',
                                  `VOLUME` BIGINT COMMENT '成交量',
                                  `TURNOVER` DECIMAL(20, 2) COMMENT '成交额',

                                  -- 1分钟数据专有字段
                                  `AVG_PRICE` DECIMAL(10, 4) COMMENT '均价(仅1分钟数据)',

                                  -- 5分钟及以上数据专有字段
                                  `CHANGE_PERCENT` DECIMAL(8, 4) COMMENT '涨跌幅(%)(仅5分钟及以上)',
                                  `CHANGE_AMOUNT` DECIMAL(10, 4) COMMENT '涨跌额(仅5分钟及以上)',
                                  `AMPLITUDE` DECIMAL(8, 4) COMMENT '振幅(%)(仅5分钟及以上)',
                                  `TURNOVER_RATE` DECIMAL(10, 4) COMMENT '换手率(%)(仅5分钟及以上)',

                                  -- 系统字段
                                  `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                  `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                  `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                  PRIMARY KEY (`R_ID`),
                                  UNIQUE KEY `IDX_LOF_MINUTE_UNIQUE` (`LOF_CODE`, `PERIOD`, `ADJUST_TYPE`, `TRADE_DATETIME`),
                                  KEY `IDX_LOF_CODE_PERIOD` (`LOF_CODE`, `PERIOD`),
                                  KEY `IDX_LOF_CODE_PERIOD_ADJUST` (`LOF_CODE`, `PERIOD`, `ADJUST_TYPE`),
                                  KEY `IDX_TRADE_DATETIME` (`TRADE_DATETIME`),
                                  KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                  KEY `IDX_PERIOD` (`PERIOD`),
                                  KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LOF基金分时行情表(东方财富)';
                                """

    def get_latest_datetime_from_table(self, lof_code, period, adjust_type=""):
        """
        获取数据库中指定LOF代码和周期的最新时间

        Args:
            lof_code: LOF代码
            period: 周期(1/5)
            adjust_type: 复权类型

        Returns:
            datetime: 最新时间，如果没有数据返回None
        """
        try:
            self.connect_db()
            sql = f"""  # nosec B608
            SELECT MAX(TRADE_DATETIME) as latest_datetime
            FROM {self.table_name}
            WHERE LOF_CODE = %s AND PERIOD = %s AND ADJUST_TYPE = %s AND IS_ACTIVE = 1
            """
            params = (lof_code, period, adjust_type)

            self.cursor.execute(sql, params)
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            self.logger.warning(f"获取最新时间失败: {e}")
            return None

    def get_lof_codes(self):
        """获取LOF代码列表"""
        try:
            # 从实时行情表获取LOF代码列表
            if self.table_exists("LOF_REALTIME_QUOTE_EM"):
                lof_codes = self.get_one_column_from_table("LOF_CODE", "LOF_REALTIME_QUOTE_EM")
                if lof_codes:
                    self.logger.info(f"从数据库获取到{len(lof_codes)}个LOF代码")
                    return sorted(lof_codes)

            # 如果没有实时行情表，使用akshare获取
            self.logger.info("从akshare获取LOF代码列表")
            df = self.fetch_ak_data("fund_lof_spot_em")
            if not df.empty and "代码" in df.columns:
                lof_codes = df["代码"].dropna().unique().tolist()
                self.logger.info(f"从akshare获取到{len(lof_codes)}个LOF代码")
                return sorted(lof_codes)

            # 备用代码列表（一些活跃的LOF基金）
            self.logger.warning("使用备用LOF代码列表")
            return ["166009", "161005", "163402", "160505", "163801"]

        except Exception as e:
            self.logger.error(f"获取LOF代码列表失败: {e}")
            return ["166009", "161005", "163402", "160505", "163801"]

    def fetch_lof_minute_data(self, lof_code, period, adjust="", start_date=None, end_date=None):
        """
        获取LOF分钟数据

        Args:
            lof_code: LOF代码
            period: 周期('1', '5', '15', '30', '60')
            adjust: 复权类型('', 'qfq', 'hfq')
            start_date: 开始时间
            end_date: 结束时间

        Returns:
            DataFrame: 数据
        """
        try:
            # 设置默认时间范围
            if not start_date:
                if period == "1":
                    # 1分钟数据只能获取近5个交易日
                    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d 09:30:00")
                else:
                    # 5分钟数据可以获取更长历史
                    start_date = "2000-01-01 09:30:00"

            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d 15:00:00")

            self.logger.info(
                f"获取 {lof_code} {period}分钟数据, 复权类型: {adjust}, 时间范围: {start_date} - {end_date}"
            )

            # 调用akshare接口
            df = self.fetch_ak_data(
                "fund_lof_hist_min_em",
                symbol=lof_code,
                period=period,
                adjust=adjust,
                start_date=start_date,
                end_date=end_date,
            )

            if df.empty:
                self.logger.warning(f"未获取到 {lof_code} 的数据")
                return pd.DataFrame()

            return df

        except Exception as e:
            self.logger.error(f"获取 {lof_code} {period}分钟数据失败: {e}")
            return pd.DataFrame()

    def process_minute_data(self, df, lof_code, period, adjust_type=""):
        """统一处理分钟数据"""
        if df.empty:
            return df

        try:
            # 创建副本避免修改原始数据
            df = df.copy()

            # 基础列映射
            column_mapping = {
                "时间": "TRADE_DATETIME",
                "开盘": "OPEN_PRICE",
                "收盘": "CLOSE_PRICE",
                "最高": "HIGH_PRICE",
                "最低": "LOW_PRICE",
                "成交量": "VOLUME",
                "成交额": "TURNOVER",
            }

            # 1分钟数据特有字段
            if period == "1" and "均价" in df.columns:
                column_mapping["均价"] = "AVG_PRICE"

            # 5分钟及以上数据特有字段
            if period != "1":
                if "涨跌幅" in df.columns:
                    column_mapping["涨跌幅"] = "CHANGE_PERCENT"
                if "涨跌额" in df.columns:
                    column_mapping["涨跌额"] = "CHANGE_AMOUNT"
                if "振幅" in df.columns:
                    column_mapping["振幅"] = "AMPLITUDE"
                if "换手率" in df.columns:
                    column_mapping["换手率"] = "TURNOVER_RATE"

            df.rename(columns=column_mapping, inplace=True)

            # 添加系统字段
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["REFERENCE_CODE"] = "LOF_MINUTE_HIST"
            df["REFERENCE_NAME"] = "LOF基金分时行情表(东方财富)"
            df["LOF_CODE"] = lof_code
            df["PERIOD"] = period
            df["ADJUST_TYPE"] = adjust_type
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"

            # 处理百分比字段(仅5分钟及以上数据)
            if period != "1":
                percent_cols = ["CHANGE_PERCENT", "AMPLITUDE", "TURNOVER_RATE"]
                for col in percent_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce") / 100

            # 处理时间格式
            df["TRADE_DATETIME"] = pd.to_datetime(
                df["TRADE_DATETIME"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M:%S")

            # 清理数据
            df = df.replace({pd.NA: None, pd.NaT: None, "NaT": None, "": None, "nan": None})

            # 将NaN转换为None
            df = df.where(pd.notnull(df), None)

            return df

        except Exception as e:
            self.logger.error(f"处理 {lof_code} {period}分钟数据时发生错误: {e}")
            return pd.DataFrame()

    def update_lof_minute_data(self, lof_codes=None):
        """更新LOF分钟数据"""
        if not lof_codes:
            lof_codes = self.get_lof_codes()

        # 限制处理数量，避免过长时间运行
        if len(lof_codes) > 50:
            lof_codes = lof_codes[:50]
            self.logger.info("限制处理LOF数量为50个")

        success_count = 0
        total_count = len(lof_codes)

        for i, lof_code in enumerate(lof_codes, 1):
            try:
                self.logger.info(f"处理 {lof_code} ({i}/{total_count})")

                # 1. 处理1分钟数据
                self.logger.info(f"处理 {lof_code} 1分钟数据")

                # 获取最新时间
                latest_time_1min = self.get_latest_datetime_from_table(lof_code, "1", "")

                # 设置开始时间（1分钟数据只能获取近5个交易日）
                if latest_time_1min:
                    start_date_1min = latest_time_1min.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    start_date_1min = (datetime.now() - timedelta(days=7)).strftime(
                        "%Y-%m-%d 09:30:00"
                    )

                # 获取1分钟数据
                df_1min = self.fetch_lof_minute_data(
                    lof_code=lof_code,
                    period="1",
                    adjust="",  # 1分钟数据不复权
                    start_date=start_date_1min,
                )

                if not df_1min.empty:
                    df_1min_processed = self.process_minute_data(df_1min, lof_code, "1", "")
                    if not df_1min_processed.empty:
                        self.save_data(
                            df_1min_processed,
                            self.table_name,
                            on_duplicate_update=True,
                            unique_keys=[
                                "LOF_CODE",
                                "PERIOD",
                                "ADJUST_TYPE",
                                "TRADE_DATETIME",
                            ],
                        )
                        self.logger.info(
                            f"{lof_code} 1分钟数据保存成功，共 {len(df_1min_processed)} 条"
                        )
                else:
                    self.logger.warning(f"{lof_code} 1分钟数据为空")

                # 2. 处理5分钟数据（前复权）
                self.logger.info(f"处理 {lof_code} 5分钟数据(前复权)")

                adjust_type = "qfq"
                latest_time_5min = self.get_latest_datetime_from_table(lof_code, "5", adjust_type)

                # 设置开始时间
                if latest_time_5min:
                    start_date_5min = latest_time_5min.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    start_date_5min = "2000-01-01 09:30:00"

                # 获取5分钟数据
                df_5min = self.fetch_lof_minute_data(
                    lof_code=lof_code,
                    period="5",
                    adjust=adjust_type,
                    start_date=start_date_5min,
                )

                if not df_5min.empty:
                    df_5min_processed = self.process_minute_data(
                        df_5min, lof_code, "5", adjust_type
                    )
                    if not df_5min_processed.empty:
                        self.save_data(
                            df_5min_processed,
                            self.table_name,
                            on_duplicate_update=True,
                            unique_keys=[
                                "LOF_CODE",
                                "PERIOD",
                                "ADJUST_TYPE",
                                "TRADE_DATETIME",
                            ],
                        )
                        self.logger.info(
                            f"{lof_code} 5分钟数据保存成功，共 {len(df_5min_processed)} 条"
                        )
                else:
                    self.logger.warning(f"{lof_code} 5分钟数据为空")

                success_count += 1

                # 适当延迟，避免请求过于频繁
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"处理 {lof_code} 失败: {e}")
                continue

        self.logger.info(f"LOF分钟数据更新完成，成功处理 {success_count}/{total_count} 个LOF")

    def run(self):
        """主运行方法"""
        try:
            # 创建表
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"创建表 {self.table_name}")

            # 更新数据
            self.update_lof_minute_data()

        except Exception as e:
            self.logger.error(f"LOF分钟数据更新失败: {e}")
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = LofMinuteHistEm()
    data_updater.run()
