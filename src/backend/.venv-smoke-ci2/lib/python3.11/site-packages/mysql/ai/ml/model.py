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
"""HeatWave ML model utilities for MySQL Connector/Python.

Provides classes to manage training, prediction, scoring, and explanations
via MySQL HeatWave stored procedures.
"""
import copy
import json

from enum import Enum
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd

from mysql.ai.utils import (
    VAR_NAME_SPACE,
    atomic_transaction,
    convert_to_df,
    execute_sql,
    format_value_sql,
    get_random_name,
    source_schema,
    sql_response_to_df,
    sql_table_from_df,
    sql_table_to_df,
    table_exists,
    temporary_sql_tables,
    validate_name,
)
from mysql.connector.abstracts import MySQLConnectionAbstract


class ML_TASK(Enum):  # pylint: disable=invalid-name
    """Enumeration of supported ML tasks for HeatWave."""

    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    FORECASTING = "forecasting"
    ANOMALY_DETECTION = "anomaly_detection"
    LOG_ANOMALY_DETECTION = "log_anomaly_detection"
    RECOMMENDATION = "recommendation"
    TOPIC_MODELING = "topic_modeling"

    @staticmethod
    def get_task_string(task: Union[str, "ML_TASK"]) -> str:
        """
        Return the string representation of a machine learning task.

        Args:
            task (Union[str, ML_TASK]): The task to convert.
                Accepts either a task enum member (ML_TASK) or a string.

        Returns:
            str: The string value of the ML task.
        """

        if isinstance(task, str):
            return task

        return task.value


class _MyModelCommon:
    """
    Common utilities and workflow for MySQL HeatWave ML models.

    This class handles model lifecycle steps such as loading, fitting, scoring,
    making predictions, and explaining models or predictions. Not intended for
    direct instantiation, but as a superclass for heatwave model wrappers.

    Attributes:
        db_connection: MySQL connector database connection.
        task: ML task, e.g., "classification" or "regression".
        model_name: Identifier of model in MySQL.
        schema_name: Database schema used for operations and temp tables.
    """

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        task: Union[str, ML_TASK] = ML_TASK.CLASSIFICATION,
        model_name: Optional[str] = None,
    ):
        """
        Instantiate _MyMLModelCommon.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-train.html
                A full list of supported tasks can be found under "Common ML_TRAIN Options"

        Args:
            db_connection: MySQL database connection.
            task: ML task type (default: "classification").
            model_name: Name to register the model within MySQL (default: None).

        Raises:
            ValueError: If the schema name is not valid
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Returns:
            None
        """
        self.db_connection = db_connection
        self.task = ML_TASK.get_task_string(task)
        self.schema_name = source_schema(db_connection)

        with atomic_transaction(self.db_connection) as cursor:
            execute_sql(cursor, "CALL sys.ML_CREATE_OR_UPGRADE_CATALOG();")

        if model_name is None:
            model_name = get_random_name(self._is_model_name_available)

        self.model_var = f"{VAR_NAME_SPACE}.{model_name}"
        self.model_var_score = f"{self.model_var}.score"

        self.model_name = model_name
        validate_name(model_name)

        with atomic_transaction(self.db_connection) as cursor:
            execute_sql(cursor, f"SET @{self.model_var} = %s;", params=(model_name,))

    def _delete_model(self) -> bool:
        """
        Deletes the model from the model catalog if present

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Returns:
            Whether the model was deleted
        """
        current_user = self._get_user()

        qualified_model_catalog = f"ML_SCHEMA_{current_user}.MODEL_CATALOG"
        delete_model = (
            f"DELETE FROM {qualified_model_catalog} "
            f"WHERE model_handle = @{self.model_var}"
        )

        with atomic_transaction(self.db_connection) as cursor:
            execute_sql(cursor, delete_model)
            return cursor.rowcount > 0

    def _get_model_info(self, model_name: str) -> Optional[dict]:
        """
        Retrieves the model info from the model_catalog

        Args:
            model_var: The model alias to retrieve

        Returns:
            The model info from the model_catalog (None if the model is not present in the catalog)

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """

        def process_col(elem: Any) -> Any:
            if isinstance(elem, str):
                try:
                    elem = json.loads(elem)
                except json.JSONDecodeError:
                    pass
            return elem

        current_user = self._get_user()

        qualified_model_catalog = f"ML_SCHEMA_{current_user}.MODEL_CATALOG"
        model_exists = (
            f"SELECT * FROM {qualified_model_catalog} WHERE model_handle = %s"
        )

        with atomic_transaction(self.db_connection) as cursor:
            execute_sql(cursor, model_exists, params=(model_name,))
            model_info_df = sql_response_to_df(cursor)

            if model_info_df.empty:
                result = None
            else:
                unprocessed_result = model_info_df.to_json(orient="records")
                unprocessed_result_json = json.loads(unprocessed_result)[0]
                result = {
                    key: process_col(elem)
                    for key, elem in unprocessed_result_json.items()
                }

            return result

    def get_model_info(self) -> Optional[dict]:
        """
        Checks if the model name is available.
        Model info is present in the catalog only if the model was previously fitted.

        Returns:
            True if the model name is not part of the model catalog

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return self._get_model_info(self.model_name)

    def _is_model_name_available(self, model_name: str) -> bool:
        """
        Checks if the model name is available

        Returns:
            True if the model name is not part of the model catalog

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return self._get_model_info(model_name) is None

    def _load_model(self) -> None:
        """
        Loads the model specified by `self.model_name` into MySQL.
        After loading, the model is ready to handle ML operations.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-model-load.html

        Raises:
            DatabaseError:
                If the model is not initialized, i.e., fit or import has not been called
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Returns:
            None
        """
        with atomic_transaction(self.db_connection) as cursor:
            load_model_query = f"CALL sys.ML_MODEL_LOAD(@{self.model_var}, NULL);"
            execute_sql(cursor, load_model_query)

    def _get_user(self) -> str:
        """
        Fetch the current database user (without host).

        Returns:
            The username string associated with the connection.

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError: If the user name includes unsupported characters
        """
        with atomic_transaction(self.db_connection) as cursor:
            cursor.execute("SELECT CURRENT_USER()")
            current_user = cursor.fetchone()[0].split("@")[0]

            return validate_name(current_user)

    def explain_model(self) -> dict:
        """
        Get model explanations, such as detailed feature importances.

        Returns:
            dict: Feature importances and model explainability data.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-model-explanations.html

        Raises:
            DatabaseError:
                If the model is not initialized, i.e., fit or import has not been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError:
                If the model does not exist in the model catalog.
                Should only occur if model was not fitted or was deleted.
        """
        self._load_model()
        with atomic_transaction(self.db_connection) as cursor:
            current_user = self._get_user()

            qualified_model_catalog = f"ML_SCHEMA_{current_user}.MODEL_CATALOG"
            explain_query = (
                f"SELECT model_explanation FROM {qualified_model_catalog} "
                f"WHERE model_handle = @{self.model_var}"
            )

            execute_sql(cursor, explain_query)
            df = sql_response_to_df(cursor)

            return df.iloc[0, 0]

    def _fit(
        self,
        table_name: str,
        target_column_name: Optional[str],
        options: Optional[dict],
    ) -> None:
        """
        Fit an ML model using a referenced SQL table and target column.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-train.html
                A full list of supported options can be found under "Common ML_TRAIN Options"

        Args:
            table_name: Name of the training data table.
            target_column_name: Name of the target/label column.
            options: Additional fit/config options (may override defaults).

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError: If the table or target_column name is not valid

        Returns:
            None
        """
        validate_name(table_name)
        if target_column_name is not None:
            validate_name(target_column_name)
            target_col_string = f"'{target_column_name}'"
        else:
            target_col_string = "NULL"

        if options is None:
            options = {}
        options = copy.deepcopy(options)
        options["task"] = self.task

        self._delete_model()

        with atomic_transaction(self.db_connection) as cursor:
            placeholders, parameters = format_value_sql(options)
            execute_sql(
                cursor,
                (
                    "CALL sys.ML_TRAIN("
                    f"'{self.schema_name}.{table_name}', "
                    f"{target_col_string}, "
                    f"{placeholders}, "
                    f"@{self.model_var}"
                    ")"
                ),
                params=parameters,
            )

    def _predict(
        self, table_name: str, output_table_name: str, options: Optional[dict]
    ) -> None:
        """
        Predict on a given data table and write results to an output table.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-predict-table.html
                A full list of supported options can be found under "ML_PREDICT_TABLE Options"

        Args:
            table_name: Name of the SQL table with input data.
            output_table_name: Name for the SQL output table to contain predictions.
            options: Optional prediction options.

        Returns:
            None

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError: If the table or output_table name is not valid
        """
        validate_name(table_name)
        validate_name(output_table_name)

        self._load_model()
        with atomic_transaction(self.db_connection) as cursor:
            placeholders, parameters = format_value_sql(options)
            execute_sql(
                cursor,
                (
                    "CALL sys.ML_PREDICT_TABLE("
                    f"'{self.schema_name}.{table_name}', "
                    f"@{self.model_var}, "
                    f"'{self.schema_name}.{output_table_name}', "
                    f"{placeholders}"
                    ")"
                ),
                params=parameters,
            )

    def _score(
        self,
        table_name: str,
        target_column_name: str,
        metric: str,
        options: Optional[dict],
    ) -> float:
        """
        Evaluate model performance with a scoring metric.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-score.html
                A full list of supported options can be found under
                "Options for Recommendation Models" and
                "Options for Anomaly Detection Models"

        Args:
            table_name: Table with features and ground truth.
            target_column_name: Column of true target labels.
            metric: String name of the metric to compute.
            options: Optional dictionary of further scoring options.

        Returns:
            float: Computed score from the ML system.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError: If the table or target_column name or metric is not valid
        """
        validate_name(table_name)
        validate_name(target_column_name)
        validate_name(metric)

        self._load_model()
        with atomic_transaction(self.db_connection) as cursor:
            placeholders, parameters = format_value_sql(options)
            execute_sql(
                cursor,
                (
                    "CALL sys.ML_SCORE("
                    f"'{self.schema_name}.{table_name}', "
                    f"'{target_column_name}', "
                    f"@{self.model_var}, "
                    "%s, "
                    f"@{self.model_var_score}, "
                    f"{placeholders}"
                    ")"
                ),
                params=[metric, *parameters],
            )
            execute_sql(cursor, f"SELECT @{self.model_var_score}")
            df = sql_response_to_df(cursor)

            return df.iloc[0, 0]

    def _explain_predictions(
        self, table_name: str, output_table_name: str, options: Optional[dict]
    ) -> pd.DataFrame:
        """
        Produce explanations for model predictions on provided data.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-explain-table.html
                A full list of supported options can be found under "ML_EXPLAIN_TABLE Options"

        Args:
            table_name: Name of the SQL table with input data.
            output_table_name: Name for the SQL table to store explanations.
            options: Optional dictionary (default:
                {"prediction_explainer": "permutation_importance"}).

        Returns:
            DataFrame: Prediction explanations from the output SQL table.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError: If the table or output_table name is not valid
        """
        validate_name(table_name)
        validate_name(output_table_name)

        if options is None:
            options = {"prediction_explainer": "permutation_importance"}

        self._load_model()

        with atomic_transaction(self.db_connection) as cursor:
            placeholders, parameters = format_value_sql(options)
            execute_sql(
                cursor,
                (
                    "CALL sys.ML_EXPLAIN_TABLE("
                    f"'{self.schema_name}.{table_name}', "
                    f"@{self.model_var}, "
                    f"'{self.schema_name}.{output_table_name}', "
                    f"{placeholders}"
                    ")"
                ),
                params=parameters,
            )
            execute_sql(cursor, f"SELECT * FROM {self.schema_name}.{output_table_name}")
            df = sql_response_to_df(cursor)

            return df


class MyModel(_MyModelCommon):
    """
    Convenience class for managing the ML workflow using pandas DataFrames.

    Methods convert in-memory DataFrames into temp SQL tables before delegating to the
    _MyMLModelCommon routines, and automatically clean up temp resources.
    """

    def fit(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
        y: Optional[Union[pd.DataFrame, np.ndarray]],
        options: Optional[dict] = None,
    ) -> None:
        """
        Fit a model using DataFrame inputs.

        If an 'id' column is defined in either dataframe, it will be used as the primary key.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-train.html
                A full list of supported options can be found under "Common ML_TRAIN Options"

        Args:
            X: Features DataFrame.
            y: (Optional) Target labels DataFrame or Series. If None, only X is used.
            options: Additional options to pass to training.

        Returns:
            None

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Combines X and y as necessary. Creates a temporary table in the schema for training,
            and deletes it afterward.
        """
        X, y = convert_to_df(X), convert_to_df(y)

        with (
            atomic_transaction(self.db_connection) as cursor,
            temporary_sql_tables(self.db_connection) as temporary_tables,
        ):
            if y is not None:
                if isinstance(y, pd.DataFrame):
                    # keep column name if it exists
                    target_column_name = y.columns[0]
                else:
                    target_column_name = get_random_name(
                        lambda name: name not in X.columns
                    )

                if target_column_name in X.columns:
                    raise ValueError(
                        f"Target column y with name {target_column_name} already present "
                        "in feature dataframe X"
                    )

                df_combined = X.copy()
                df_combined[target_column_name] = y
                final_df = df_combined
            else:
                target_column_name = None
                final_df = X

            _, table_name = sql_table_from_df(cursor, self.schema_name, final_df)
            temporary_tables.append((self.schema_name, table_name))

            self._fit(table_name, target_column_name, options)

    def predict(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
        options: Optional[dict] = None,
    ) -> pd.DataFrame:
        """
        Generate model predictions using DataFrame input.

        If an 'id' column is defined in either dataframe, it will be used as the primary key.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-predict-table.html
                A full list of supported options can be found under "ML_PREDICT_TABLE Options"

        Args:
            X: DataFrame containing prediction features (no labels).
            options: Additional prediction settings.

        Returns:
            DataFrame with prediction results as returned by HeatWave.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Temporary SQL tables are created and deleted for input/output.
        """
        X = convert_to_df(X)

        with (
            atomic_transaction(self.db_connection) as cursor,
            temporary_sql_tables(self.db_connection) as temporary_tables,
        ):
            _, table_name = sql_table_from_df(cursor, self.schema_name, X)
            temporary_tables.append((self.schema_name, table_name))

            output_table_name = get_random_name(
                lambda table_name: not table_exists(
                    cursor, self.schema_name, table_name
                )
            )
            temporary_tables.append((self.schema_name, output_table_name))

            self._predict(table_name, output_table_name, options)
            predictions = sql_table_to_df(cursor, self.schema_name, output_table_name)

            # ml_results is text but known to always follow JSON format
            predictions["ml_results"] = predictions["ml_results"].map(json.loads)

            return predictions

    def score(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
        y: Union[pd.DataFrame, np.ndarray],
        metric: str,
        options: Optional[dict] = None,
    ) -> float:
        """
        Score the model using X/y data and a selected metric.

        If an 'id' column is defined in either dataframe, it will be used as the primary key.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-score.html
                A full list of supported options can be found under
                "Options for Recommendation Models" and
                "Options for Anomaly Detection Models"

        Args:
            X: DataFrame of features.
            y: DataFrame or Series of labels.
            metric: Metric name (e.g., "balanced_accuracy").
            options: Optional ml scoring options.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Returns:
            float: Computed score.
        """
        X, y = convert_to_df(X), convert_to_df(y)

        with (
            atomic_transaction(self.db_connection) as cursor,
            temporary_sql_tables(self.db_connection) as temporary_tables,
        ):
            target_column_name = get_random_name(lambda name: name not in X.columns)
            df_combined = X.copy()
            df_combined[target_column_name] = y
            final_df = df_combined

            _, table_name = sql_table_from_df(cursor, self.schema_name, final_df)
            temporary_tables.append((self.schema_name, table_name))

            score = self._score(table_name, target_column_name, metric, options)

            return score

    def explain_predictions(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
        options: Dict = None,
    ) -> pd.DataFrame:
        """
        Explain model predictions using provided data.

        If an 'id' column is defined in either dataframe, it will be used as the primary key.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-explain-table.html
                A full list of supported options can be found under
                "ML_EXPLAIN_TABLE Options"

        Args:
            X: DataFrame for which predictions should be explained.
            options: Optional dictionary of explainability options.

        Returns:
            DataFrame containing explanation details (feature attributions, etc.)

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported, or if the model is not initialized,
                i.e., fit or import has not been called
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Temporary input/output tables are cleaned up after explanation.
        """
        X = convert_to_df(X)

        with (
            atomic_transaction(self.db_connection) as cursor,
            temporary_sql_tables(self.db_connection) as temporary_tables,
        ):

            _, table_name = sql_table_from_df(cursor, self.schema_name, X)
            temporary_tables.append((self.schema_name, table_name))

            output_table_name = get_random_name(
                lambda table_name: not table_exists(
                    cursor, self.schema_name, table_name
                )
            )
            temporary_tables.append((self.schema_name, output_table_name))

            explanations = self._explain_predictions(
                table_name, output_table_name, options
            )

            return explanations
