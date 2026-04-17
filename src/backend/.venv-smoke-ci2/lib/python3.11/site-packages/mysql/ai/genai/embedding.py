# Copyright (c) 2025 Oracle and/or its affiliates.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2.0, as
# published by the Free Software Foundation.
#
# This program is designed to work with certain software (including
# but not limited to OpenSSL) that is licensed under separate terms,
# as designated in a particular file or component or in included license
# documentation. The authors of MySQL hereby grant you an
# additional permission to link the program and your derivative works
# with the separately licensed software that they have either included with
# the program or referenced in the documentation.
#
# Without limiting anything contained in the foregoing, this file,
# which is part of MySQL Connector/Python, is also subject to the
# Universal FOSS Exception, version 1.0, a copy of which can be found at
# http://oss.oracle.com/licenses/universal-foss-exception.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License, version 2.0, for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA

"""Embeddings integration utilities for MySQL Connector/Python.

Provides MyEmbeddings class to generate embeddings via MySQL HeatWave
using ML_EMBED_TABLE and ML_EMBED_ROW.
"""

from typing import Dict, List, Optional

import pandas as pd

from langchain_core.embeddings import Embeddings
from pydantic import PrivateAttr

from mysql.ai.utils import (
    atomic_transaction,
    execute_sql,
    format_value_sql,
    source_schema,
    sql_table_from_df,
    sql_table_to_df,
    temporary_sql_tables,
)
from mysql.connector.abstracts import MySQLConnectionAbstract


class MyEmbeddings(Embeddings):
    """
    Embedding generator class that uses a MySQL database to compute embeddings for input text.

    This class batches input text into temporary SQL tables, invokes MySQL's ML_EMBED_TABLE
    to generate embeddings, and retrieves the results as lists of floats.

    Attributes:
        _db_connection (MySQLConnectionAbstract): MySQL connection used for all database operations.
        schema_name (str): Name of the database schema to use.
        options_placeholder (str): SQL-ready placeholder string for ML_EMBED_TABLE options.
        options_params (dict): Dictionary of concrete option values to be passed as SQL parameters.
    """

    _db_connection: MySQLConnectionAbstract = PrivateAttr()

    def __init__(
        self, db_connection: MySQLConnectionAbstract, options: Optional[Dict] = None
    ):
        """
        Initialize MyEmbeddings with a database connection and optional embedding parameters.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-embed-row.html
                A full list of supported options can be found under "options"

        NOTE: The supported "options" are the intersection of the options provided in
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-embed-row.html
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-embed-table.html

        Args:
            db_connection: Active MySQL connector database connection.
            options: Optional dictionary of options for embedding operations.

        Raises:
            ValueError: If the schema name is not valid
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        super().__init__()
        self._db_connection = db_connection
        self.schema_name = source_schema(db_connection)
        options = options or {}
        self.options_placeholder, self.options_params = format_value_sql(options)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of input texts using the MySQL ML embedding procedure.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-embed-table.html

        Args:
            texts: List of input strings to embed.

        Returns:
            List of lists of floats, with each inner list containing the embedding for a text.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError:
                If one or more text entries were unable to be embedded.

        Implementation notes:
            - Creates a temporary table to pass input text to the MySQL embedding service.
            - Adds a primary key to ensure results preserve input order.
            - Calls ML_EMBED_TABLE and fetches the resulting embeddings.
            - Deletes the temporary table after use to avoid polluting the database.
            - Embedding vectors are extracted from the "embeddings" column of the result table.
        """
        if not texts:
            return []

        df = pd.DataFrame({"id": range(len(texts)), "text": texts})

        with (
            atomic_transaction(self._db_connection) as cursor,
            temporary_sql_tables(self._db_connection) as temporary_tables,
        ):
            qualified_table_name, table_name = sql_table_from_df(
                cursor, self.schema_name, df
            )
            temporary_tables.append((self.schema_name, table_name))

            # ML_EMBED_TABLE expects input/output columns and options as parameters
            embed_query = (
                "CALL sys.ML_EMBED_TABLE("
                f"'{qualified_table_name}.text', "
                f"'{qualified_table_name}.embeddings', "
                f"{self.options_placeholder}"
                ")"
            )
            execute_sql(cursor, embed_query, params=self.options_params)

            # Read back all columns, including "embeddings"
            df_embeddings = sql_table_to_df(cursor, self.schema_name, table_name)

            if df_embeddings["embeddings"].isnull().any() or any(
                e is None for e in df_embeddings["embeddings"]
            ):
                raise ValueError(
                    "Failure to generate embeddings for one or more text entry."
                )

            # Convert fetched embeddings to lists of floats
            embeddings = df_embeddings["embeddings"].tolist()
            embeddings = [list(e) for e in embeddings]

            return embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        Generate an embedding for a single text string.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-embed-row.html

        Args:
            text: The input string to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Example:
            >>> MyEmbeddings(db_conn).embed_query("Hello world")
            [0.1, 0.2, ...]
        """
        with atomic_transaction(self._db_connection) as cursor:
            execute_sql(
                cursor,
                f'SELECT sys.ML_EMBED_ROW("%s", {self.options_placeholder})',
                params=(text, *self.options_params),
            )
            return list(cursor.fetchone()[0])
