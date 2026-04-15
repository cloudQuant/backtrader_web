import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class OpenFundHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 开放式基金历史数据表
        self.table_name = "OPEN_FUND_HIST_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `OPEN_FUND_HIST_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'OPEN_FUND_HIST' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '开放式基金历史数据表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `DATA_TYPE` VARCHAR(20) NOT NULL COMMENT '数据类型(单位净值/累计净值/累计收益率/同类排名等)',

                              -- 净值/收益率/排名数据
                              `DATE` DATE NOT NULL COMMENT '日期',
                              `VALUE` DECIMAL(20, 6) COMMENT '数值',
                              `VALUE2` DECIMAL(20, 6) COMMENT '数值2(用于存储排名等额外数据)',
                              `VALUE3` DECIMAL(20, 6) COMMENT '数值3(用于存储总排名等额外数据)',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_OPEN_FUND_HIST_UNIQUE` (`FUND_CODE`, `DATA_TYPE`, `DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_DATA_TYPE` (`DATA_TYPE`),
                              KEY `IDX_DATE` (`DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='开放式基金历史数据表(东方财富)';
                            """

        # 支持的数据类型
        self.supported_indicators = [
            "unit_nav",  # 单位净值走势
            "acc_nav",  # 累计净值走势
            "yield_rate",  # 累计收益率走势
            "rank",  # 同类排名走势
            "rank_pct",  # 同类排名百分比
            "dividend",  # 分红送配详情
            "split",  # 拆分详情
        ]

        # 数据类型映射
        self.indicator_mapping = {
            "unit_nav": "单位净值走势",
            "acc_nav": "累计净值走势",
            "yield_rate": "累计收益率走势",
            "rank": "同类排名走势",
            "rank_pct": "同类排名百分比",
            "dividend": "分红送配详情",
            "split": "拆分详情",
        }

    def get_latest_date_from_table(self, fund_code, data_type):
        """
        获取指定基金和数据类型的最新日期

        Args:
            fund_code: 基金代码
            data_type: 数据类型

        Returns:
            datetime: 最新日期，如果没有数据返回None
        """
        try:
            self.connect_db()
            sql = f"""  # nosec B608
            SELECT MAX(`DATE`) as latest_date
            FROM {self.table_name}
            WHERE FUND_CODE = %s
            AND DATA_TYPE = %s
            AND IS_ACTIVE = 1
            """

            self.cursor.execute(sql, (fund_code, data_type))
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            self.logger.warning(f"获取最新日期失败: {e}")
            return None

    def fetch_fund_hist_data(self, fund_code, indicator="unit_nav", period="成立来"):
        """
        获取基金历史数据

        Args:
            fund_code: 基金代码
            indicator: 数据类型，支持: unit_nav/acc_nav/yield_rate/rank/rank_pct/dividend/split
            period: 周期(仅对累计收益率走势有效)

        Returns:
            pd.DataFrame: 处理后的数据
        """
        try:
            if indicator not in self.supported_indicators:
                self.logger.error(f"不支持的数据类型: {indicator}")
                return None

            indicator_cn = self.indicator_mapping.get(indicator, indicator)
            self.logger.info(f"开始获取基金[{fund_code}]{indicator_cn}历史数据...")

            # 获取数据
            if indicator == "yield_rate":
                df = self.fetch_ak_data(
                    "fund_open_fund_info_em",
                    symbol=fund_code,
                    indicator=indicator_cn,
                    period=period,
                )
            else:
                df = self.fetch_ak_data(
                    "fund_open_fund_info_em", symbol=fund_code, indicator=indicator_cn
                )

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金[{fund_code}]{indicator_cn}历史数据")
                return None

            # 处理不同数据类型的列名
            df = self._process_dataframe(df, indicator)

            # 添加基金代码和数据类型
            df["FUND_CODE"] = fund_code
            df["DATA_TYPE"] = indicator

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["DATA_TYPE"] + "_" + df["DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "OPEN_FUND_HIST"
            df["REFERENCE_NAME"] = f"开放式基金{indicator_cn}历史数据(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            self.logger.info(f"成功获取基金[{fund_code}]{indicator_cn}{len(df)}条历史数据")
            return df

        except Exception as e:
            self.logger.error(
                f"获取基金[{fund_code}]{indicator_cn}历史数据失败: {e}", exc_info=True
            )
            return None

    def _process_dataframe(self, df, indicator):
        """
        处理不同数据类型的DataFrame

        Args:
            df: 原始DataFrame
            indicator: 数据类型

        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        # 重命名列
        if indicator == "unit_nav":
            # 单位净值走势
            df = df.rename(columns={"净值日期": "DATE", "单位净值": "VALUE", "日增长率": "VALUE2"})
        elif indicator == "acc_nav":
            # 累计净值走势
            df = df.rename(columns={"净值日期": "DATE", "累计净值": "VALUE"})
        elif indicator == "yield_rate":
            # 累计收益率走势
            df = df.rename(columns={"日期": "DATE", "累计收益率": "VALUE"})
        elif indicator == "rank":
            # 同类排名走势
            df = df.rename(
                columns={
                    "报告日期": "DATE",
                    "同类型排名-每日近三月排名": "VALUE",
                    "总排名-每日近三月排名": "VALUE2",
                }
            )
        elif indicator == "rank_pct":
            # 同类排名百分比
            df = df.rename(
                columns={
                    "报告日期": "DATE",
                    "同类型排名-每日近3月收益排名百分比": "VALUE",
                }
            )
        elif indicator in ["dividend", "split"]:
            # 分红送配详情和拆分详情
            # 这两个类型的数据结构较复杂，这里简单处理，实际使用时可能需要调整
            df["DATE"] = (
                df.get("权益登记日", pd.NaT)
                if indicator == "dividend"
                else df.get("拆分折算日", pd.NaT)
            )
            df["VALUE"] = (
                df.get("每份分红", 0) if indicator == "dividend" else df.get("拆分折算比例", 1)
            )

        # 转换日期格式
        if "DATE" in df.columns:
            df["DATE"] = pd.to_datetime(df["DATE"]).dt.date

        # 转换数值类型
        for col in ["VALUE", "VALUE2", "VALUE3"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def save_fund_hist_data(self, df, indicator):
        """
        保存基金历史数据到数据库

        Args:
            df: 要保存的数据
            indicator: 数据类型

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        # 获取需要的列
        columns = [
            "R_ID",
            "REFERENCE_CODE",
            "REFERENCE_NAME",
            "FUND_CODE",
            "DATA_TYPE",
            "DATE",
            "VALUE",
            "VALUE2",
            "VALUE3",
            "IS_ACTIVE",
            "DATA_SOURCE",
            "CREATEDATE",
            "CREATEUSER",
            "UPDATEDATE",
            "UPDATEUSER",
        ]

        # 确保所有需要的列都存在
        df = df[[col for col in columns if col in df.columns]]

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def run(self, fund_codes=None, indicators=None, period="成立来"):
        """
        执行数据获取和保存

        Args:
            fund_codes: 基金代码列表，如果为None则从数据库获取所有基金
            indicators: 数据类型列表，如果为None则获取所有支持的类型
            period: 周期(仅对累计收益率走势有效)

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行开放式基金历史数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 如果未指定基金代码，则从数据库获取所有基金代码
            if fund_codes is None:
                fund_codes = self._get_all_fund_codes()
                if not fund_codes:
                    self.logger.error("未获取到基金代码")
                    return False

            # 如果未指定数据类型，则获取所有支持的类型
            if indicators is None:
                indicators = self.supported_indicators

            total_success = True
            total_count = 0

            # 遍历基金代码和数据类型
            for fund_code in fund_codes:
                for indicator in indicators:
                    try:
                        # 获取最新数据
                        df = self.fetch_fund_hist_data(fund_code, indicator, period)

                        if df is None or df.empty:
                            continue

                        # 保存数据
                        success = self.save_fund_hist_data(df, indicator)

                        if success:
                            total_count += len(df)
                            self.logger.info(
                                f"成功保存基金[{fund_code}]{self.indicator_mapping.get(indicator, indicator)} {len(df)}条历史数据"
                            )
                        else:
                            self.logger.error(
                                f"保存基金[{fund_code}]{self.indicator_mapping.get(indicator, indicator)}历史数据失败"
                            )
                            total_success = False

                        # 避免请求过于频繁
                        time.sleep(1)

                    except Exception as e:
                        self.logger.error(
                            f"处理基金[{fund_code}]{self.indicator_mapping.get(indicator, indicator)}历史数据时出错: {e}",
                            exc_info=True,
                        )
                        total_success = False
                        continue

            self.logger.info(f"开放式基金历史数据更新完成，共处理{total_count}条数据")
            return total_success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()

    def _get_all_fund_codes(self):
        """
        从数据库获取所有基金代码

        Returns:
            list: 基金代码列表
        """
        try:
            self.connect_db()
            sql = """
            SELECT DISTINCT FUND_CODE
            FROM OPEN_FUND_DAILY_EM
            WHERE IS_ACTIVE = 1
            ORDER BY FUND_CODE
            """
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return [row[0] for row in result] if result else []
        except Exception as e:
            self.logger.error(f"获取基金代码列表失败: {e}")
            return []


if __name__ == "__main__":
    # 示例：更新指定基金的单位净值和累计净值历史数据
    fund_codes = [
        "000001",
        "000002",
    ]  # 可以指定要更新的基金代码，如果为None则更新所有基金
    indicators = ["unit_nav", "acc_nav"]  # 可以指定要更新的数据类型

    data_updater = OpenFundHistEm()
    data_updater.run(fund_codes=fund_codes, indicators=indicators)
