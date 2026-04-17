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

"""Classifier utilities for MySQL Connector/Python.

Provides a scikit-learn compatible classifier backed by HeatWave ML.
"""
from typing import Optional, Union

import numpy as np
import pandas as pd
from sklearn.base import ClassifierMixin

from mysql.ai.ml.base import MyBaseMLModel
from mysql.ai.ml.model import ML_TASK
from mysql.ai.utils import copy_dict

from mysql.connector.abstracts import MySQLConnectionAbstract


class MyClassifier(MyBaseMLModel, ClassifierMixin):
    """
    MySQL HeatWave scikit-learn compatible classifier estimator.

    Provides prediction and probability output from a model deployed in MySQL,
    and manages fit, explain, and prediction options as per HeatWave ML interface.

    Attributes:
        predict_extra_options (dict): Dictionary of optional parameters passed through
            to the MySQL backend for prediction and probability inference.
        _model (MyModel): Underlying interface for database model operations.
        fit_extra_options (dict): See MyBaseMLModel.

    Args:
        db_connection (MySQLConnectionAbstract): Active MySQL connector DB connection.
        model_name (str, optional): Custom name for the model.
        fit_extra_options (dict, optional): Extra options for fitting.
        explain_extra_options (dict, optional): Extra options for explanations.
        predict_extra_options (dict, optional): Extra options for predict/predict_proba.

    Methods:
        predict(X): Predict class labels.
        predict_proba(X): Predict class probabilities.
    """

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        model_name: Optional[str] = None,
        fit_extra_options: Optional[dict] = None,
        explain_extra_options: Optional[dict] = None,
        predict_extra_options: Optional[dict] = None,
    ):
        """
        Initialize a MyClassifier.

        Args:
            db_connection: Active MySQL connector database connection.
            model_name: Optional, custom model name.
            fit_extra_options: Optional fit options.
            explain_extra_options: Optional explain options.
            predict_extra_options: Optional predict/predict_proba options.

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        MyBaseMLModel.__init__(
            self,
            db_connection,
            ML_TASK.CLASSIFICATION,
            model_name=model_name,
            fit_extra_options=fit_extra_options,
        )
        self.predict_extra_options = copy_dict(predict_extra_options)
        self.explain_extra_options = copy_dict(explain_extra_options)

    def predict(
        self, X: Union[pd.DataFrame, np.ndarray]
    ) -> np.ndarray:  # pylint: disable=invalid-name
        """
        Predict class labels for the input features using the MySQL model.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-predict-table.html
                A full list of supported options can be found under "ML_PREDICT_TABLE Options"

        Args:
            X: Input samples as a numpy array or pandas DataFrame.

        Returns:
            ndarray: Array of predicted class labels, shape (n_samples,).

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        result = self._model.predict(X, options=self.predict_extra_options)
        return result["Prediction"].to_numpy()

    def predict_proba(
        self, X: Union[pd.DataFrame, np.ndarray]
    ) -> np.ndarray:  # pylint: disable=invalid-name
        """
        Predict class probabilities for the input features using the MySQL model.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-predict-table.html
                A full list of supported options can be found under "ML_PREDICT_TABLE Options"

        Args:
            X: Input samples as a numpy array or pandas DataFrame.

        Returns:
            ndarray: Array of shape (n_samples, n_classes) with class probabilities.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        result = self._model.predict(X, options=self.predict_extra_options)

        classes = sorted(result["ml_results"].iloc[0]["probabilities"].keys())

        return np.stack(
            result["ml_results"].map(
                lambda ml_result: [
                    ml_result["probabilities"][class_name] for class_name in classes
                ]
            )
        )

    def explain_predictions(
        self, X: Union[pd.DataFrame, np.ndarray]
    ) -> pd.DataFrame:  # pylint: disable=invalid-name
        """
        Explain model predictions using provided data.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwaml-ml-explain-table.html
                A full list of supported options can be found under "ML_EXPLAIN_TABLE Options"

        Args:
            X: DataFrame for which predictions should be explained.

        Returns:
            DataFrame containing explanation details (feature attributions, etc.)

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Temporary input/output tables are cleaned up after explanation.
        """
        self._model.explain_predictions(X, options=self.explain_extra_options)
