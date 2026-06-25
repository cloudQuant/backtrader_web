"""
Movie Boxoffice Realtime

数据源: 艺恩 Endata
函数: movie_boxoffice_realtime
频率: hourly
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.common._endata_yien import EndataYienClient


class MovieBoxofficeRealtime(AkshareToMySql):
    """Movie Boxoffice Realtime"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MOVIE_BOXOFFICE_REALTIME"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MOVIE_BOXOFFICE_REALTIME` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `Irank` INT COMMENT 'rank',
            `MovieID` BIGINT COMMENT 'movie id',
            `EntMovieID` BIGINT COMMENT 'endata movie id',
            `MovieName` VARCHAR(255) COMMENT 'movie name',
            `EnMovieName` VARCHAR(255) COMMENT 'english movie name',
            `BoxOffice` DOUBLE COMMENT 'box office',
            `TotalBoxOffice` DOUBLE COMMENT 'total box office',
            `BoxOfficePercent` DOUBLE COMMENT 'box office percent',
            `ShowCount` BIGINT COMMENT 'show count',
            `AudienceCount` BIGINT COMMENT 'audience count',
            `ReleaseDay` INT COMMENT 'release day',
            `ReleaseDate` DATE COMMENT 'release date',
            `data_date` DATE COMMENT 'data date',
            `snapshot_date` DATE COMMENT 'snapshot date',
            `source_update_time` VARCHAR(20) COMMENT 'source update time',
            `fetched_at` DATETIME COMMENT 'fetch time',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
        UNIQUE KEY uk_movie_snapshot (`MovieID`, `data_date`, `source_update_time`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Movie Boxoffice Realtime'
    """

    def fetch_data(self, **kwargs):
        """Fetch current-day movie box-office data from the current Endata API.

        Args:
            date: Optional date in YYYYMMDD or YYYY-MM-DD format.

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            df = EndataYienClient().fetch_movie_realtime(kwargs.get("date"))

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["MovieID", "data_date", "source_update_time"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = MovieBoxofficeRealtime()
    script.fetch_data()


if __name__ == "__main__":
    main()
