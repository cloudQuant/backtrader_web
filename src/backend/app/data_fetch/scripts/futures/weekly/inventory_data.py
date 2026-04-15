from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesInventoryData(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_INVENTORY_DATA"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_INVENTORY_DATA (
                                    R_ID VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '品种代码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '品种名称',
                                    DATA_SOURCE VARCHAR(100) NOT NULL COMMENT '信息来源: 99期货网/东方财富网',
                                    BASEDATE DATE NOT NULL COMMENT '数据日期',
                                    CLOSE_PRICE DECIMAL(16,4) COMMENT '收盘价',
                                    INVENTORY_AMOUNT BIGINT COMMENT '库存数量',
                                    INVENTORY_CHANGE BIGINT COMMENT '库存数量变化',
                                    -- 系统字段
                                    CREATEDATE DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                                    UPDATEDATE DATETIME COMMENT '更新时间',
                                    UPDATEUSER VARCHAR(50) COMMENT '更新用户',

                                    -- 主键约束
                                    PRIMARY KEY (R_ID),

                                    -- 唯一约束
                                --     UNIQUE KEY UK_INVENTORY_DATA (REFERENCE_CODE, BASEDATE),

                                    -- 普通索引
                                    INDEX IDX_INVENTORY_DATE (BASEDATE),
                                    INDEX IDX_INVENTORY_SOURCE (DATA_SOURCE),
                                    INDEX IDX_INVENTORY_CODE (REFERENCE_CODE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='期货库存数据表';


                                """

    def run(self):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取期货库存数据")
        name_symbol_dict = {
            "沪铅": "PB",
            "沪铝": "AL",
            "苯乙烯": "EB",
            "多晶硅": "ps",
            "锡": "SN",
            "沪铜": "CU",
            "镍": "NI",
            "沪锌": "ZN",
            "丁二烯橡胶": "BR",
            "20号胶": "nr",
            "纸浆": "SP",
            "原木": "LG",
            "玉米淀粉": "CS",
            "玉米": "C",
            "菜籽": "RS",
            "不锈钢": "SS",
            "短纤": "PF",
            "集运指数(欧线)": "ec",
            "沪银": "AG",
            "液化石油气": "PG",
            "鸡蛋": "JD",
            "沪金": "AU",
            "低硫燃料油": "lu",
            "豆一": "A",
            "玻璃": "FG",
            "燃油": "FU",
            "菜油": "OI",
            "红枣": "CJ",
            "沥青": "BU",
            "郑棉": "CF",
            "白糖": "SR",
            "菜粕": "RM",
            "PTA": "TA",
            "碳酸锂": "lc",
            "工业硅": "si",
            "尿素": "UR",
            "瓶片": "PR",
            "锰硅": "SM",
            "棉纱": "CY",
            "硅铁": "SF",
            "纯碱": "SA",
            "烧碱": "SH",
            "豆二": "B",
            "塑料": "L",
            "聚丙烯": "PP",
            "焦炭": "J",
            "生猪": "LH",
            "PVC": "V",
            "焦煤": "JM",
            "氧化铝": "AO",
            "乙二醇": "EG",
            "甲醇": "MA",
            "对二甲苯": "PX",
            "橡胶": "RU",
            "豆油": "Y",
            "棕榈": "P",
            "铁矿石": "I",
            "豆粕": "M",
            "花生": "PK",
            "苹果": "AP",
            "热卷": "HC",
            "螺纹钢": "RB",
            "铸造铝合金": "AD",
        }
        table_name = "FUTURES_INVENTORY_DATA"
        for name in name_symbol_dict:
            try:
                df = self.fetch_ak_data("futures_inventory_99", name)
                if df is not None and not df.empty:
                    df.columns = ["BASEDATE", "CLOSE_PRICE", "INVENTORY_AMOUNT"]
                    df["R_ID"] = [self.get_uuid() for i in range(len(df))]
                    df["REFERENCE_CODE"] = name_symbol_dict[name]
                    df["REFERENCE_NAME"] = name
                    df["SOURCE"] = "99期货网"
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    latest_date = self.get_latest_date(
                        table_name, "BASEDATE", conditions={"REFERENCE_NAME": name}
                    )
                    df = df[df["BASEDATE"] >= latest_date]
                    if len(df) > 0:
                        self.save_data(df, table_name, ignore_duplicates=True)
                    else:
                        self.logger.warning(f"没有{name}最新的库存数据")
                else:
                    self.logger.warning(f"没有获取到{name}的库存数据")
            except Exception as e:
                self.logger.warning(f"获取{name}库存数据失败: {e}")


if __name__ == "__main__":
    data_updater = FuturesInventoryData()
    data_updater.run()
