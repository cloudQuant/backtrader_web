import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockBoardIndustryMinEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_BOARD_INDUSTRY_MIN_EM"
        self.create_table_sql = r"""
                                CREATE TABLE STOCK_BOARD_INDUSTRY_MIN_EM (
                                    R_ID VARCHAR(36) NOT NULL COMMENT 'UUID生成的唯一标识',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '行业板块代码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '行业板块名称',
                                    BASEDATE DATE GENERATED ALWAYS AS (DATE(DATETIME)) STORED COMMENT '数据日期(冗余字段)',
                                    CREATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建日期',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                    UPDATEDATE TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日期',
                                    UPDATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                    -- 业务字段
                                    PERIOD VARCHAR(10) NOT NULL COMMENT 'K线周期: 1, 5, 15, 30, 60 分钟',
                                    DATETIME DATETIME NOT NULL COMMENT '日期时间',

                                    -- 行情数据
                                    OPEN_PRICE DECIMAL(18, 4) COMMENT '开盘价',
                                    CLOSE_PRICE DECIMAL(18, 4) COMMENT '收盘价',
                                    HIGH_PRICE DECIMAL(18, 4) COMMENT '最高价',
                                    LOW_PRICE DECIMAL(18, 4) COMMENT '最低价',
                                    LATEST_PRICE DECIMAL(18, 4) COMMENT '最新价(1分钟K线)',
                                    CHANGE_PERCENT DECIMAL(10, 4) COMMENT '涨跌幅(%)',
                                    CHANGE_AMOUNT DECIMAL(18, 4) COMMENT '涨跌额',
                                    VOLUME BIGINT COMMENT '成交量(手)',
                                    TURNOVER DECIMAL(20, 4) COMMENT '成交额(元)',
                                    AMPLITUDE DECIMAL(10, 4) COMMENT '振幅(%)',
                                    TURNOVER_RATIO DECIMAL(10, 4) COMMENT '换手率(%)',

                                    PRIMARY KEY (R_ID),
                                    UNIQUE KEY uk_industry_min (REFERENCE_CODE, DATETIME, PERIOD),
                                    KEY idx_datetime (DATETIME),
                                    KEY idx_basedate (BASEDATE),
                                    KEY idx_industry (REFERENCE_CODE),
                                    KEY idx_period (PERIOD)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东方财富-行业板块分时行情数据表';
                                """

    def run(self, period="5"):
        """
        更新东方财富行业板块分时行情数据

        Args:
            period (str): K线周期，可选值: "1", "5", "15", "30", "60" 分钟
        """
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info(f"开始更新行业板块{period}分钟K线数据")

        try:
            # 1. 获取所有行业板块代码和名称
            industry_df = self.get_data_by_columns(
                table_name="STOCK_BOARD_INDUSTRY_EM",
                column_list=["BOARD_CODE", "BOARD_NAME"],
            )

            if industry_df.empty:
                self.logger.info(
                    "行业板块列表为空，尝试直接从 AkShare 拉取行业列表并写入 STOCK_BOARD_INDUSTRY_EM"
                )
                try:
                    seed_df = self.fetch_ak_data("stock_board_industry_name_em")
                    if seed_df is not None and not seed_df.empty:
                        seed_df.columns = [
                            "RANK_NUM",
                            "BOARD_NAME",
                            "BOARD_CODE",
                            "LATEST_PRICE",
                            "CHANGE_AMOUNT",
                            "CHANGE_PERCENT",
                            "TOTAL_MARKET_VALUE",
                            "TURNOVER_RATIO",
                            "UP_COUNT",
                            "DOWN_COUNT",
                            "LEADER_STOCK_NAME",
                            "LEADER_STOCK_CHANGE_PERCENT",
                        ]
                        seed_df["R_ID"] = [self.get_uuid() for _ in range(len(seed_df))]
                        seed_df["REFERENCE_CODE"] = seed_df["BOARD_CODE"]
                        seed_df["REFERENCE_NAME"] = seed_df["BOARD_NAME"]
                        seed_df["BASEDATE"] = self.get_current_date()

                        if self.table_exists("STOCK_BOARD_INDUSTRY_EM"):
                            self.save_data(seed_df, "STOCK_BOARD_INDUSTRY_EM")
                except Exception as e:
                    self.logger.warning(f"拉取/落库行业板块列表失败: {e}")

                industry_df = self.get_data_by_columns(
                    table_name="STOCK_BOARD_INDUSTRY_EM",
                    column_list=["BOARD_CODE", "BOARD_NAME"],
                )

            if industry_df.empty:
                self.logger.warning(
                    "未找到行业板块数据，请先运行 1102_stock_board_industry_em 获取行业列表"
                )
                return False

            industry_df = (
                industry_df.rename(columns={"BOARD_CODE": "symbol", "BOARD_NAME": "name"})
                .drop_duplicates(subset=["symbol"])
                .reset_index(drop=True)
            )

            self.logger.info(f"共获取到 {len(industry_df)} 个行业板块")
            self.connect_db()

            # 2. 遍历每个行业，获取分时数据
            total_new_records = 0

            for _, row in industry_df.iterrows():
                symbol = row["symbol"]
                name = row["name"]

                try:
                    self.logger.info(f"正在获取 {name}({symbol}) 的{period}分钟K线数据...")

                    # 获取分时数据
                    min_df = self.fetch_ak_data("stock_board_industry_hist_min_em", name, period)
                    # min_df = ak.stock_board_industry_hist_min_em(symbol=name, period=period)

                    if min_df is None or min_df.empty:
                        self.logger.warning(f"未获取到 {name}({symbol}) 的{period}分钟K线数据")
                        continue

                    self.logger.info(
                        f"成功获取 {name}({symbol}) 的 {len(min_df)} 条{period}分钟K线数据"
                    )

                    # 重命名列
                    if period == "1":
                        # 1分钟K线列名
                        min_df.columns = [
                            "DATETIME",
                            "OPEN_PRICE",
                            "CLOSE_PRICE",
                            "HIGH_PRICE",
                            "LOW_PRICE",
                            "VOLUME",
                            "TURNOVER",
                            "LATEST_PRICE",
                        ]
                        # 添加其他可能为空的列
                        min_df["CHANGE_PERCENT"] = None
                        min_df["CHANGE_AMOUNT"] = None
                        min_df["AMPLITUDE"] = None
                        min_df["TURNOVER_RATIO"] = None
                    else:
                        # 其他周期K线列名
                        min_df.columns = [
                            "DATETIME",
                            "OPEN_PRICE",
                            "CLOSE_PRICE",
                            "HIGH_PRICE",
                            "LOW_PRICE",
                            "CHANGE_PERCENT",
                            "CHANGE_AMOUNT",
                            "VOLUME",
                            "TURNOVER",
                            "AMPLITUDE",
                            "TURNOVER_RATIO",
                        ]
                        min_df["LATEST_PRICE"] = None

                    # 添加系统字段
                    min_df["R_ID"] = [self.get_uuid() for _ in range(len(min_df))]
                    min_df["REFERENCE_CODE"] = symbol
                    min_df["REFERENCE_NAME"] = name
                    min_df["PERIOD"] = period

                    # 转换日期时间格式
                    min_df["DATETIME"] = pd.to_datetime(min_df["DATETIME"])

                    # 转换数值类型
                    numeric_cols = [
                        "OPEN_PRICE",
                        "CLOSE_PRICE",
                        "HIGH_PRICE",
                        "LOW_PRICE",
                        "LATEST_PRICE",
                        "CHANGE_PERCENT",
                        "CHANGE_AMOUNT",
                        "VOLUME",
                        "TURNOVER",
                        "AMPLITUDE",
                        "TURNOVER_RATIO",
                    ]

                    for col in numeric_cols:
                        if col in min_df.columns:
                            min_df[col] = pd.to_numeric(min_df[col], errors="coerce")

                    # 保存到数据库
                    if not min_df.empty:
                        # 先删除当天的数据，避免重复
                        if self.connection is None:
                            self.connect_db()

                        # 获取要删除的日期范围
                        min_date = min_df["DATETIME"].min().strftime("%Y-%m-%d")
                        max_date = min_df["DATETIME"].max().strftime("%Y-%m-%d")
                        min_df["DATETIME"] = min_df["DATETIME"].dt.strftime("%Y-%m-%d %H:%M:%S")
                        with self.connection.cursor() as cursor:
                            delete_sql = """
                                         DELETE \
                                         FROM STOCK_BOARD_INDUSTRY_MIN_EM
                                         WHERE REFERENCE_CODE = %s
                                           AND PERIOD = %s
                                           AND DATE(DATETIME) BETWEEN %s AND %s \
                                         """
                            cursor.execute(delete_sql, (symbol, period, min_date, max_date))
                            self.connection.commit()

                        # 保存新数据
                        self.save_data(
                            min_df,
                            "STOCK_BOARD_INDUSTRY_MIN_EM",
                            # columns=[
                            #     'R_ID', 'REFERENCE_CODE', 'REFERENCE_NAME', 'DATETIME',
                            #     'PERIOD', 'OPEN_PRICE', 'CLOSE_PRICE', 'HIGH_PRICE',
                            #     'LOW_PRICE', 'LATEST_PRICE', 'CHANGE_PERCENT',
                            #     'CHANGE_AMOUNT', 'VOLUME', 'TURNOVER', 'AMPLITUDE',
                            #     'TURNOVER_RATIO'
                            # ]
                        )
                        total_new_records += len(min_df)
                        self.logger.info(
                            f"成功保存 {name}({symbol}) 的 {len(min_df)} 条{period}分钟K线数据"
                        )

                except Exception as e:
                    self.logger.error(f"处理行业 {name}({symbol}) 时出错: {str(e)}", exc_info=True)
                    continue

            self.logger.info(
                f"行业板块{period}分钟K线数据更新完成，共新增 {total_new_records} 条记录"
            )
            return True

        except Exception as e:
            self.logger.error(f"更新行业板块{period}分钟K线数据失败: {str(e)}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    stock_data = StockBoardIndustryMinEm()
    stock_data.run("1")
    # stock_data.run("5")
