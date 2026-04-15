import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesNewsShmet(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_NEWS_SHMET"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_NEWS_SHMET` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'SHMET_NEWS' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海金属网期货资讯' COMMENT '参考名称',

                                      -- 基本信息
                                      `PUBLISH_TIME` DATETIME NOT NULL COMMENT '发布时间',
                                      `CONTENT` TEXT NOT NULL COMMENT '新闻内容',
                                      `CATEGORY` VARCHAR(20) NOT NULL COMMENT '资讯类别(铜/铝/铅/锌/镍/锡/贵金属/小金属/要闻/VIP/财经/全部)',
                                      `SYMBOL` VARCHAR(20) NOT NULL COMMENT '查询的品种代码',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '上海金属网' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_SHMET_NEWS_UNIQUE` (`PUBLISH_TIME`, `CONTENT`(200), `SYMBOL`),
                                      KEY `IDX_SHMET_PUBLISH_TIME` (`PUBLISH_TIME`),
                                      KEY `IDX_SHMET_CATEGORY` (`CATEGORY`),
                                      KEY `IDX_SHMET_SYMBOL` (`SYMBOL`),
                                      KEY `IDX_SHMET_IS_ACTIVE` (`IS_ACTIVE`),
                                      FULLTEXT INDEX `IDX_FT_CONTENT` (`CONTENT`) WITH PARSER ngram
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海金属网期货资讯表';

                                """

    def run(self):
        """
        Fetches and stores futures news from SHMET for all relevant categories.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("Starting SHMET futures news update.")
        table_name = "FUTURES_NEWS_SHMET"
        symbols = [
            "全部",
            "要闻",
            "VIP",
            "财经",
            "铜",
            "铝",
            "铅",
            "锌",
            "镍",
            "锡",
            "贵金属",
            "小金属",
        ]

        for symbol in symbols:
            try:
                self.logger.info(f"Processing news for category: {symbol}")

                # 1. Get the latest publish time for the current symbol
                latest_time = self.get_latest_date(
                    self.table_name, "PUBLISH_TIME", conditions={"SYMBOL": symbol}
                )
                if latest_time:
                    self.logger.info(
                        f"Latest news for '{symbol}' in DB is from {latest_time}. Fetching newer items."
                    )
                else:
                    self.logger.info(
                        f"No existing news for '{symbol}' found. Performing a full fetch."
                    )

                # 2. Fetch Data
                # df = ak.futures_news_shmet(symbol=symbol)
                df = self.fetch_ak_data("futures_news_shmet", symbol)
                time.sleep(3)  # Be respectful to the server

                if df.empty:
                    self.logger.warning(f"No news returned for category: {symbol}")
                    continue

                # 3. Data Transformation
                df.rename(
                    columns={"发布时间": "PUBLISH_TIME", "内容": "CONTENT"},
                    inplace=True,
                )

                # Convert publish time to timezone-aware datetime objects
                df["PUBLISH_TIME"] = pd.to_datetime(df["PUBLISH_TIME"], errors="coerce")
                df.dropna(subset=["PUBLISH_TIME"], inplace=True)

                # 4. Filter for new records
                if latest_time:
                    df = df[df["PUBLISH_TIME"] > latest_time]

                if df.empty:
                    self.logger.info(f"No new news to update for category: {symbol}")
                    continue

                self.logger.info(f"Found {len(df)} new news items for category: {symbol}")

                # Add custom and default columns
                df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                df["REFERENCE_CODE"] = "SHMET_NEWS"
                df["REFERENCE_NAME"] = "上海金属网期货资讯"
                df["CATEGORY"] = symbol
                df["SYMBOL"] = symbol
                df["IS_ACTIVE"] = 1
                df["DATA_SOURCE"] = "上海金属网"
                df["CREATEUSER"] = "system"
                df["UPDATEUSER"] = "system"

                # Convert datetime to string for MySQL
                df["PUBLISH_TIME"] = df["PUBLISH_TIME"].dt.strftime("%Y-%m-%d %H:%M:%S")

                # 5. Save to DB
                self.save_data(df, table_name, unique_keys=["PUBLISH_TIME", "SYMBOL"])

            except Exception as e:
                self.logger.error(
                    f"Failed to process news for category '{symbol}': {e}",
                    exc_info=True,
                )
                continue

        self.logger.info("SHMET futures news update finished.")


if __name__ == "__main__":
    data_updater = FuturesNewsShmet()
    data_updater.run()
