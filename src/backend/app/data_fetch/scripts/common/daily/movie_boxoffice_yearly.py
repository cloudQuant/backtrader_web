"""
Movie Boxoffice Yearly

数据源: 艺恩 Endata
函数: movie_boxoffice_yearly
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.common._endata_yien import EndataYienClient


class MovieBoxofficeYearly(AkshareToMySql):
    """Movie Boxoffice Yearly"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MOVIE_BOXOFFICE_YEARLY"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MOVIE_BOXOFFICE_YEARLY` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `Irank` INT COMMENT 'year rank',
            `SourceIrank` INT COMMENT 'source all-year rank',
            `MovieID` BIGINT COMMENT 'movie id',
            `EntMovieID` BIGINT COMMENT 'endata movie id',
            `MovieName` VARCHAR(255) COMMENT 'movie name',
            `EnMovieName` VARCHAR(255) COMMENT 'english movie name',
            `BoxOffice` DOUBLE COMMENT 'year box office',
            `TotalBoxOffice` DOUBLE COMMENT 'total box office',
            `ShowCount` BIGINT COMMENT 'show count',
            `AudienceCount` BIGINT COMMENT 'audience count',
            `ReleaseDate` DATE COMMENT 'release date',
            `Year` INT COMMENT 'source year',
            `data_year` INT COMMENT 'data year',
            `data_date` DATE COMMENT 'data date',
            `fetched_at` DATETIME COMMENT 'fetch time',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
        UNIQUE KEY uk_movie_year (`MovieID`, `data_year`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Movie Boxoffice Yearly'
    """

    def fetch_data(self, **kwargs):
        """Fetch yearly movie box-office data from the current Endata API.

        Args:
            date: Optional year or date in YYYYMMDD / YYYY-MM-DD format.

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            df = EndataYienClient().fetch_movie_year(kwargs.get("date"))

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["MovieID", "data_year"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = MovieBoxofficeYearly()
    script.fetch_data()


if __name__ == "__main__":
    main()
