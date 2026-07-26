"""
Movie Boxoffice Weekly

数据源: 艺恩 Endata
函数: movie_boxoffice_weekly
频率: weekly
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.common._endata_yien import EndataYienClient


class MovieBoxofficeWeekly(AkshareToMySql):
    """Movie Boxoffice Weekly"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MOVIE_BOXOFFICE_WEEKLY"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MOVIE_BOXOFFICE_WEEKLY` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `Irank` INT COMMENT 'rank',
            `MovieID` BIGINT COMMENT 'movie id',
            `MovieName` VARCHAR(255) COMMENT 'movie name',
            `BoxOffice` DOUBLE COMMENT 'box office',
            `ShowCount` BIGINT COMMENT 'show count',
            `AudienceCount` BIGINT COMMENT 'audience count',
            `BoxOfficePercent` DOUBLE COMMENT 'box office percent',
            `ShowCountPercent` DOUBLE COMMENT 'show count percent',
            `AudienceCountPercent` DOUBLE COMMENT 'audience count percent',
            `Attendance` DOUBLE COMMENT 'attendance',
            `week_id` BIGINT COMMENT 'endata week id',
            `week_start` DATE COMMENT 'week start',
            `week_end` DATE COMMENT 'week end',
            `data_date` DATE COMMENT 'data date',
            `source_update_time` VARCHAR(20) COMMENT 'source update time',
            `fetched_at` DATETIME COMMENT 'fetch time',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
        UNIQUE KEY uk_movie_week (`MovieID`, `week_id`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Movie Boxoffice Weekly'
    """

    def fetch_data(self, **kwargs):
        """Fetch public weekly movie box-office chart data from the current Endata API.

        Args:
            date: Optional date in YYYYMMDD or YYYY-MM-DD format.

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            df = EndataYienClient().fetch_movie_week(kwargs.get("date"))

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["MovieID", "week_id"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = MovieBoxofficeWeekly()
    script.fetch_data()


if __name__ == "__main__":
    main()
