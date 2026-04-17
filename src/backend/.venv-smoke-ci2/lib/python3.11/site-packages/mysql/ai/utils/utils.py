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
"""General utilities for AI features in MySQL Connector/Python.

Includes helpers for:
- defensive dict copying
- temporary table lifecycle management
- SQL execution and result conversions
- DataFrame to/from SQL table utilities
- schema/table/column name validation
- array-like to DataFrame conversion
"""

import copy
import json
import random
import re
import string

from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from mysql.ai.utils.atomic_cursor import atomic_transaction

from mysql.connector.abstracts import MySQLConnectionAbstract
from mysql.connector.cursor import MySQLCursorAbstract
from mysql.connector.types import ParamsSequenceOrDictType

VAR_NAME_SPACE = "mysql_ai"
RANDOM_TABLE_NAME_LENGTH = 32

PD_TO_SQL_DTYPE_MAPPING = {
    "int64": "BIGINT",
    "float64": "DOUBLE",
    "object": "LONGTEXT",
    "bool": "BOOLEAN",
    "datetime64[ns]": "DATETIME",
}

DEFAULT_SCHEMA = "mysql_ai"

# Misc Utilities


def copy_dict(options: Optional[dict]) -> dict:
    """
    Make a defensive copy of a dictionary, or return an empty dict if None.

    Args:
        options: param dict or None

    Returns:
        dict
    """
    if options is None:
        return {}

    return copy.deepcopy(options)


@contextmanager
def temporary_sql_tables(
    db_connection: MySQLConnectionAbstract,
) -> Iterator[list[tuple[str, str]]]:
    """
    Context manager to track and automatically clean up temporary SQL tables.

    Args:
        db_connection: Database connection object used to create and delete tables.

    Returns:
        None

    Raises:
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.

    Yields:
        temporary_tables: List of (schema_name, table_name) tuples created during the
            context. All tables in this list are deleted on context exit.
    """
    temporary_tables: List[Tuple[str, str]] = []
    try:
        yield temporary_tables
    finally:
        with atomic_transaction(db_connection) as cursor:
            for schema_name, table_name in temporary_tables:
                delete_sql_table(cursor, schema_name, table_name)


def execute_sql(
    cursor: MySQLCursorAbstract, query: str, params: ParamsSequenceOrDictType = None
) -> None:
    """
    Execute an SQL query with optional parameters using the given cursor.

    Args:
        cursor: MySQLCursorAbstract object to execute the query.
        query: SQL query string to execute.
        params: Optional sequence or dict providing parameters for the query.

    Raises:
        DatabaseError:
            If the provided SQL query/params are invalid
            If the query is valid but the sql raises as an exception
            If a database connection issue occurs.
            If an operational error occurs during execution.

    Returns:
        None
    """
    cursor.execute(query, params or ())


def _get_name() -> str:
    """
    Generate a random uppercase string of fixed length for table names.

    Returns:
        Random string of length RANDOM_TABLE_NAME_LENGTH.
    """
    char_set = string.ascii_uppercase
    return "".join(random.choices(char_set, k=RANDOM_TABLE_NAME_LENGTH))


def get_random_name(condition: Callable[[str], bool], max_calls: int = 100) -> str:
    """
    Generate a random string name that satisfies a given condition.

    Args:
        condition: Callable that takes a generated name and returns True if it is valid.
        max_calls: Maximum number of attempts before giving up (default 100).

    Returns:
        A random string that fulfills the provided condition.

    Raises:
        RuntimeError: If the maximum number of attempts is reached without success.
    """
    for _ in range(max_calls):
        if condition(name := _get_name()):
            return name
    # condition never met
    raise RuntimeError("Reached max tries without successfully finding a unique name")


# Format conversions


def format_value_sql(value: Any) -> Tuple[str, List[Any]]:
    """
    Convert a Python value into its SQL-compatible string representation and parameters.

    Args:
        value: The value to format.

    Returns:
        Tuple containing:
            - A string for substitution into a SQL query.
            - A list of parameters to be bound into the query.
    """
    if isinstance(value, (dict, list)):
        if len(value) == 0:
            return "%s", [None]
        return "CAST(%s as JSON)", [json.dumps(value)]
    return "%s", [value]


def sql_response_to_df(cursor: MySQLCursorAbstract) -> pd.DataFrame:
    """
    Convert the results of a cursor's last executed query to a pandas DataFrame.

    Args:
        cursor: MySQLCursorAbstract with a completed query.

    Returns:
        DataFrame with data from the cursor.

    Raises:
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.
            If a compatible SELECT query wasn't the last statement ran
    """

    def _json_processor(elem: Optional[str]) -> Optional[dict]:
        return json.loads(elem) if elem is not None else None

    def _default_processor(elem: Any) -> Any:
        return elem

    idx_to_processor = {}
    for idx, col in enumerate(cursor.description):
        if col[1] == 245:
            # 245 is the MySQL type code for JSON
            idx_to_processor[idx] = _json_processor
        else:
            idx_to_processor[idx] = _default_processor

    rows = cursor.fetchall()

    # Process results
    processed_rows = []
    for row in rows:
        processed_row = list(row)

        for idx, elem in enumerate(row):
            processed_row[idx] = idx_to_processor[idx](elem)

        processed_rows.append(processed_row)

    return pd.DataFrame(processed_rows, columns=cursor.column_names)


def sql_table_to_df(
    cursor: MySQLCursorAbstract, schema_name: str, table_name: str
) -> pd.DataFrame:
    """
    Load the entire contents of a SQL table into a pandas DataFrame.

    Args:
        cursor: MySQLCursorAbstract to execute the query.
        schema_name: Name of the schema containing the table.
        table_name: Name of the table to fetch.

    Returns:
        DataFrame containing all rows from the specified table.

    Raises:
        DatabaseError:
            If the table does not exist
            If a database connection issue occurs.
            If an operational error occurs during execution.
        ValueError: If the schema or table name is not valid
    """
    validate_name(schema_name)
    validate_name(table_name)

    execute_sql(cursor, f"SELECT * FROM {schema_name}.{table_name}")
    return sql_response_to_df(cursor)


# Table operations


def table_exists(
    cursor: MySQLCursorAbstract, schema_name: str, table_name: str
) -> bool:
    """
    Check whether a table exists in a specific schema.

    Args:
        cursor: MySQLCursorAbstract object to execute the query.
        schema_name: Name of the database schema.
        table_name: Name of the table.

    Returns:
        True if the table exists, False otherwise.

    Raises:
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.
        ValueError: If the schema or table name is not valid
    """
    validate_name(schema_name)
    validate_name(table_name)

    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema_name, table_name),
    )
    return cursor.fetchone() is not None


def delete_sql_table(
    cursor: MySQLCursorAbstract, schema_name: str, table_name: str
) -> None:
    """
    Drop a table from the SQL database if it exists.

    Args:
        cursor: MySQLCursorAbstract to execute the drop command.
        schema_name: Name of the schema.
        table_name: Name of the table to delete.

    Returns:
        None

    Raises:
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.
        ValueError: If the schema or table name is not valid
    """
    validate_name(schema_name)
    validate_name(table_name)

    execute_sql(cursor, f"DROP TABLE IF EXISTS {schema_name}.{table_name}")


def extend_sql_table(
    cursor: MySQLCursorAbstract,
    schema_name: str,
    table_name: str,
    df: pd.DataFrame,
    col_name_to_placeholder_string: Dict[str, str] = None,
) -> None:
    """
    Insert all rows from a pandas DataFrame into an existing SQL table.

    Args:
        cursor: MySQLCursorAbstract for execution.
        schema_name: Name of the database schema.
        table_name: Table to insert new rows into.
        df: DataFrame containing the rows to insert.
        col_name_to_placeholder_string:
            Optional mapping of column names to custom SQL value/placeholder
            strings.

    Returns:
        None

    Raises:
        DatabaseError:
            If the rows could not be inserted into the table, e.g., a type or shape issue
            If a database connection issue occurs.
            If an operational error occurs during execution.
        ValueError: If the schema or table name is not valid
    """
    if col_name_to_placeholder_string is None:
        col_name_to_placeholder_string = {}

    validate_name(schema_name)
    validate_name(table_name)
    for col in df.columns:
        validate_name(str(col))

    qualified_table_name = f"{schema_name}.{table_name}"

    # Iterate over all rows in the DataFrame to build insert statements row by row
    for row in df.values:
        placeholders, params = [], []
        for elem, col in zip(row, df.columns):
            elem = elem.item() if hasattr(elem, "item") else elem

            if col in col_name_to_placeholder_string:
                elem_placeholder, elem_params = col_name_to_placeholder_string[col], [
                    str(elem)
                ]
            else:
                elem_placeholder, elem_params = format_value_sql(elem)

            placeholders.append(elem_placeholder)
            params.extend(elem_params)

        cols_sql = ", ".join([str(col) for col in df.columns])
        placeholders_sql = ", ".join(placeholders)
        insert_sql = (
            f"INSERT INTO {qualified_table_name} "
            f"({cols_sql}) VALUES ({placeholders_sql})"
        )
        execute_sql(cursor, insert_sql, params=params)


def sql_table_from_df(
    cursor: MySQLCursorAbstract, schema_name: str, df: pd.DataFrame
) -> Tuple[str, str]:
    """
    Create a new SQL table with a random name, and populate it with data from a DataFrame.

    If an 'id' column is defined in the dataframe, it will be used as the primary key.

    Args:
        cursor: MySQLCursorAbstract for executing SQL.
        schema_name: Schema in which to create the table.
        df: DataFrame containing the data to be inserted.

    Returns:
        Tuple (qualified_table_name, table_name): The schema-qualified and
        unqualified table names.

    Raises:
        RuntimeError: If a random available table name could not be found.
        ValueError: If any schema, table, or a column name is invalid.
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.
    """
    table_name = get_random_name(
        lambda table_name: not table_exists(cursor, schema_name, table_name)
    )
    qualified_table_name = f"{schema_name}.{table_name}"

    validate_name(schema_name)
    validate_name(table_name)
    for col in df.columns:
        validate_name(str(col))

    columns_sql = []
    for col, dtype in df.dtypes.items():
        # Map pandas dtype to SQL type, fallback is VARCHAR
        sql_type = PD_TO_SQL_DTYPE_MAPPING.get(str(dtype), "LONGTEXT")
        validate_name(str(col))
        columns_sql.append(f"{col} {sql_type}")

    columns_str = ", ".join(columns_sql)

    has_id_col = any(col.lower() == "id" for col in df.columns)
    if has_id_col:
        columns_str += ", PRIMARY KEY (id)"

    # Create table with generated columns
    create_table_sql = f"CREATE TABLE {qualified_table_name} ({columns_str})"
    execute_sql(cursor, create_table_sql)

    try:
        # Insert provided data into new table
        extend_sql_table(cursor, schema_name, table_name, df)
    except Exception:  # pylint: disable=broad-exception-caught
        # Delete table before we lose access to it
        delete_sql_table(cursor, schema_name, table_name)
        raise
    return qualified_table_name, table_name


def validate_name(name: str) -> str:
    """
    Validate that the string is a legal SQL identifier (letters, digits, underscores).

    Args:
        name: Name (schema, table, or column) to validate.

    Returns:
        The validated name.

    Raises:
        ValueError: If the name does not meet format requirements.
    """
    # Accepts only letters, digits, and underscores; change as needed
    if not (isinstance(name, str) and re.match(r"^[A-Za-z0-9_]+$", name)):
        raise ValueError(f"Unsupported name format {name}")

    return name


def source_schema(db_connection: MySQLConnectionAbstract) -> str:
    """
    Retrieve the name of the currently selected schema, or set and ensure the default schema.

    Args:
        db_connection: MySQL connector database connection object.

    Returns:
        Name of the schema (database in use).

    Raises:
        ValueError: If the schema name is not valid
        DatabaseError:
            If a database connection issue occurs.
            If an operational error occurs during execution.
    """
    schema = db_connection.database
    if schema is None:
        schema = DEFAULT_SCHEMA

        with atomic_transaction(db_connection) as cursor:
            create_database_stmt = f"CREATE DATABASE IF NOT EXISTS {schema}"
            execute_sql(cursor, create_database_stmt)

    validate_name(schema)

    return schema


def is_table_empty(
    cursor: MySQLCursorAbstract, schema_name: str, table_name: str
) -> bool:
    """
    Determine if a given SQL table is empty.

    Args:
        cursor: MySQLCursorAbstract with access to the database.
        schema_name: Name of the schema containing the table.
        table_name: Name of the table to check.

    Returns:
        True if the table has no rows, False otherwise.

    Raises:
        DatabaseError:
            If the table does not exist
            If a database connection issue occurs.
            If an operational error occurs during execution.
        ValueError: If the schema or table name is not valid
    """
    validate_name(schema_name)
    validate_name(table_name)

    cursor.execute(f"SELECT 1 FROM {schema_name}.{table_name} LIMIT 1")
    return cursor.fetchone() is None


def convert_to_df(
    arr: Optional[Union[pd.DataFrame, pd.Series, np.ndarray]],
    col_prefix: str = "feature",
) -> Optional[pd.DataFrame]:
    """
    Convert input data to a pandas DataFrame if necessary.

    Args:
        arr: Input data as a pandas DataFrame, NumPy ndarray, pandas Series, or None.

    Returns:
        If the input is None, returns None.
        Otherwise, returns a DataFrame backed by the same underlying data whenever
        possible (except in cases where pandas or NumPy must copy, such as for
        certain views or non-contiguous arrays).

    Notes:
        - If an ndarray is passed, column names will be integer indices (0, 1, ...).
        - If a DataFrame is passed, column names and indices are preserved.
        - The returned DataFrame is a shallow copy and shares data with the original
          input when possible; however, copies may still occur for certain input
          types or memory layouts.
    """
    if arr is None:
        return None

    if isinstance(arr, pd.DataFrame):
        return pd.DataFrame(arr)
    if isinstance(arr, pd.Series):
        return arr.to_frame()

    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    col_names = [f"{col_prefix}_{idx}" for idx in range(arr.shape[1])]

    return pd.DataFrame(arr, columns=col_names, copy=False)
