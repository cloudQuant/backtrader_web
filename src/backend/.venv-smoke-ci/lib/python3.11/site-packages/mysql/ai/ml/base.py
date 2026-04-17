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

"""Base classes for MySQL HeatWave ML estimators for Connector/Python.

Implements a scikit-learn-compatible base estimator wrapping server-side ML.
"""
from typing import Optional, Union

import pandas as pd

from sklearn.base import BaseEstimator

from mysql.connector.abstracts import MySQLConnectionAbstract
from mysql.ai.ml.model import ML_TASK, MyModel
from mysql.ai.utils import copy_dict


class MyBaseMLModel(BaseEstimator):
    """
    Base class for MySQL HeatWave machine learning estimators.

    Implements the scikit-learn API and core model management logic,
    including fit, explain, serialization, and dynamic option handling.
    For use as a base class by classifiers, regressors, transformers, and outlier models.

    Args:
        db_connection (MySQLConnectionAbstract): An active MySQL connector database connection.
        task (str): ML task type, e.g. "classification" or "regression".
        model_name (str, optional): Custom name for the deployed model.
        fit_extra_options (dict, optional): Extra options for fitting.

    Attributes:
        _model: Underlying database helper for fit/predict/explain.
        fit_extra_options: User-provided options for fitting.
    """

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        task: Union[str, ML_TASK],
        model_name: Optional[str] = None,
        fit_extra_options: Optional[dict] = None,
    ):
        """
        Initialize a MyBaseMLModel with connection, task, and option parameters.

        Args:
            db_connection: Active MySQL connector database connection.
            task: String label of ML task (e.g. "classification").
            model_name: Optional custom model name.
            fit_extra_options: Optional extra fit options.

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        self._model = MyModel(db_connection, task=task, model_name=model_name)
        self.fit_extra_options = copy_dict(fit_extra_options)

    def fit(
        self,
        X: pd.DataFrame,  # pylint: disable=invalid-name
        y: Optional[pd.DataFrame] = None,
    ) -> "MyBaseMLModel":
        """
        Fit the underlying ML model using pandas DataFrames.
        Delegates to MyMLModelPandasHelper.fit.

        Args:
            X: Features DataFrame.
            y: (Optional) Target labels DataFrame or Series.

        Returns:
            self

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Additional temp SQL resources may be created and cleaned up during the operation.
        """
        self._model.fit(X, y, self.fit_extra_options)
        return self

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
        return self._model._delete_model()

    def get_model_info(self) -> Optional[dict]:
        """
        Checks if the model name is available. Model info will only be present in the
        catalog if the model has previously been fitted.

        Returns:
            True if the model name is not part of the model catalog

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return self._model.get_model_info()
