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
"""Generic transformer utilities for MySQL Connector/Python.

Provides a scikit-learn compatible Transformer using HeatWave for fit/transform
and scoring operations.
"""
from typing import Optional, Union

import numpy as np
import pandas as pd
from sklearn.base import TransformerMixin

from mysql.ai.ml.base import MyBaseMLModel
from mysql.ai.ml.model import ML_TASK
from mysql.ai.utils import copy_dict
from mysql.connector.abstracts import MySQLConnectionAbstract


class MyGenericTransformer(MyBaseMLModel, TransformerMixin):
    """
    MySQL HeatWave scikit-learn compatible generic transformer.

    Can be used as the transformation step in an sklearn pipeline. Implements fit, transform,
    explain, and scoring capability, passing options for server-side transform logic.

    Args:
        db_connection (MySQLConnectionAbstract): Active MySQL connector database connection.
        task (str): ML task type for transformer (default: "classification").
        score_metric (str): Scoring metric to request from backend (default: "balanced_accuracy").
        model_name (str, optional): Custom name for the deployed model.
        fit_extra_options (dict, optional): Extra fit options.
        transform_extra_options (dict, optional): Extra options for transformations.
        score_extra_options (dict, optional): Extra options for scoring.

    Attributes:
        score_metric (str): Name of the backend metric to use for scoring
            (e.g. "balanced_accuracy").
        score_extra_options (dict): Dictionary of optional scoring parameters;
            passed to backend score.
        transform_extra_options (dict): Dictionary of inference (/predict)
            parameters for the backend.
        fit_extra_options (dict): See MyBaseMLModel.
        _model (MyModel): Underlying interface for database model operations.

    Methods:
        fit(X, y): Fit the underlying model using the provided features/targets.
        transform(X): Transform features using the backend model.
        score(X, y): Score data using backend metric and options.
    """

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        task: Union[str, ML_TASK] = ML_TASK.CLASSIFICATION,
        score_metric: str = "balanced_accuracy",
        model_name: Optional[str] = None,
        fit_extra_options: Optional[dict] = None,
        transform_extra_options: Optional[dict] = None,
        score_extra_options: Optional[dict] = None,
    ):
        """
        Initialize transformer with required and optional arguments.

        Args:
            db_connection: Active MySQL backend database connection.
            task: ML task type for transformer.
            score_metric: Requested backend scoring metric.
            model_name: Optional model name for storage.
            fit_extra_options: Optional extra options for fitting.
            transform_extra_options: Optional extra options for transformation/inference.
            score_extra_options: Optional extra scoring options.

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        MyBaseMLModel.__init__(
            self,
            db_connection,
            task,
            model_name=model_name,
            fit_extra_options=fit_extra_options,
        )

        self.score_metric = score_metric
        self.score_extra_options = copy_dict(score_extra_options)

        self.transform_extra_options = copy_dict(transform_extra_options)

    def transform(
        self, X: pd.DataFrame
    ) -> pd.DataFrame:  # pylint: disable=invalid-name
        """
        Transform input data to model predictions using the underlying helper.

        Args:
            X: DataFrame of features to predict/transform.

        Returns:
            pd.DataFrame: Results of transformation as returned by backend.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return self._model.predict(X, options=self.transform_extra_options)

    def score(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
        y: Union[pd.DataFrame, np.ndarray],
    ) -> float:
        """
        Score the transformed data using the backend scoring interface.

        Args:
            X: Transformed features.
            y: Target labels or data for scoring.

        Returns:
            float: Score based on backend metric.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return self._model.score(
            X, y, self.score_metric, options=self.score_extra_options
        )
