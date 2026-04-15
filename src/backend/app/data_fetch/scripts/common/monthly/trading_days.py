import argparse
import logging
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class TradingDaysUpdater(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "TRADING_DAYS"
        self.create_table_sql = """
            CREATE TABLE `TRADING_DAYS` (
                `R_ID` VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                `BASEDATE` DATE NOT NULL COMMENT '数据日期',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日',
                `YEAR` INT COMMENT '年份',
                `MONTH` INT COMMENT '月份',
                `DAY` INT COMMENT '日',
                `WEEKDAY` INT COMMENT '星期几(0=周一)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经' COMMENT '数据来源',
                `CREATEDATE` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                `UPDATEDATE` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新用户',

                PRIMARY KEY (`R_ID`),
                UNIQUE KEY `uk_trade_date` (`TRADE_DATE`),
                KEY `idx_basedate` (`BASEDATE`),
                KEY `idx_year_month` (`YEAR`, `MONTH`),
                KEY `idx_is_active` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票交易日历表';
        """

    def fetch_trading_days(self):
        """
        从AKShare获取交易日历数据

        Returns:
            DataFrame: 处理后的交易日历数据
        """
        try:
            self.logger.info("Fetching trading days from Sina Finance via AKShare")

            # 使用父类的fetch_ak_data方法，使用默认参数
            df = self.fetch_ak_data("tool_trade_date_hist_sina")

            if df is None or df.empty:
                self.logger.warning("No trading days data found")
                return pd.DataFrame()

            self.logger.info(f"Fetched {len(df)} trading days records")

            # 处理日期列
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date

            # 过滤无效日期
            df = df.dropna(subset=["trade_date"])

            # 重命名列
            df = df.rename(columns={"trade_date": "TRADE_DATE"})

            # 添加日期相关字段
            df["TRADE_DATE_DT"] = pd.to_datetime(df["TRADE_DATE"])
            df["YEAR"] = df["TRADE_DATE_DT"].dt.year
            df["MONTH"] = df["TRADE_DATE_DT"].dt.month
            df["DAY"] = df["TRADE_DATE_DT"].dt.day
            df["WEEKDAY"] = df["TRADE_DATE_DT"].dt.weekday  # 0=Monday

            # 删除临时列
            df = df.drop("TRADE_DATE_DT", axis=1)

            # 添加元数据列
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["BASEDATE"] = date.today()
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "新浪财经"
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"

            # 定义最终列顺序
            final_columns = [
                "R_ID",
                "BASEDATE",
                "TRADE_DATE",
                "YEAR",
                "MONTH",
                "DAY",
                "WEEKDAY",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEUSER",
                "UPDATEUSER",
            ]

            # 确保所有列都存在
            for col in final_columns:
                if col not in df.columns:
                    df[col] = None

            # 去重并返回
            result_df = df[final_columns].drop_duplicates(subset=["TRADE_DATE"], keep="first")

            # 按交易日期排序
            result_df = result_df.sort_values("TRADE_DATE").reset_index(drop=True)

            self.logger.info(f"Processed {len(result_df)} unique trading days records")

            # 显示数据范围信息
            if not result_df.empty:
                min_date = result_df["TRADE_DATE"].min()
                max_date = result_df["TRADE_DATE"].max()
                self.logger.info(f"Trading days range: {min_date} to {max_date}")

            return result_df

        except Exception as e:
            self.logger.error(f"Error fetching trading days: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self):
        """
        执行交易日历更新任务

        Returns:
            bool: 执行是否成功
        """
        try:
            self.logger.info("Starting trading days data collection")

            # 确保表存在
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # 获取数据
            df = self.fetch_trading_days()
            if not df.empty:
                # 先清空旧数据（因为是全量更新）
                self.logger.info("Clearing existing trading days data")
                self.connect_db()
                clear_sql = f"DELETE FROM {self.table_name}"  # nosec B608
                self.cursor.execute(clear_sql)
                self.connection.commit()
                self.disconnect_db()

                # 保存新数据
                return self.save_data(
                    df=df.replace(np.nan, None),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["TRADE_DATE"],
                )

            self.logger.warning("No trading days data to process")
            return False

        except Exception as e:
            self.logger.error(f"Error in trading days collection: {str(e)}", exc_info=True)
            return False

    def get_latest_trading_day(self):
        """
        获取最新的交易日

        Returns:
            date: 最新交易日，如果没有数据则返回None
        """
        try:
            self.connect_db()
            sql = f"SELECT MAX(TRADE_DATE) as latest_date FROM {self.table_name} WHERE IS_ACTIVE = 1"  # nosec B608
            self.cursor.execute(sql)
            result = self.cursor.fetchone()
            self.disconnect_db()

            if result and result[0]:
                return result[0]
            return None

        except Exception as e:
            self.logger.error(f"Error getting latest trading day: {str(e)}")
            return None

    def is_trading_day(self, check_date):
        """
        检查指定日期是否为交易日

        Args:
            check_date: 要检查的日期

        Returns:
            bool: 是否为交易日
        """
        try:
            self.connect_db()
            sql = f"SELECT COUNT(*) FROM {self.table_name} WHERE TRADE_DATE = %s AND IS_ACTIVE = 1"  # nosec B608
            self.cursor.execute(sql, (check_date,))
            result = self.cursor.fetchone()
            self.disconnect_db()

            return result[0] > 0 if result else False

        except Exception as e:
            self.logger.error(f"Error checking trading day: {str(e)}")
            return False


def main():
    """主函数：配置日志和解析命令行参数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Update stock trading days calendar from Sina Finance"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--check-date",
        type=str,
        help="Check if a specific date (YYYY-MM-DD) is a trading day",
    )

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        # 创建实例
        trading_days_updater = TradingDaysUpdater(logger=logger)

        # 如果指定了检查日期
        if args.check_date:
            try:
                check_date = datetime.strptime(args.check_date, "%Y-%m-%d").date()
                is_trading = trading_days_updater.is_trading_day(check_date)
                status = "a trading day" if is_trading else "NOT a trading day"
                logger.info("Date %s is %s", check_date, status)
                sys.exit(0)
            except ValueError:
                logger.error("Invalid date format. Please use YYYY-MM-DD")
                sys.exit(1)

        # 运行更新任务
        success = trading_days_updater.run()

        # 显示最新交易日
        if success:
            latest_date = trading_days_updater.get_latest_trading_day()
            if latest_date:
                logger.info(f"Latest trading day in database: {latest_date}")

        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
