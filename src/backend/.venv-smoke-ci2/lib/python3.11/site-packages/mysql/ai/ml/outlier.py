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

"""Outlier/anomaly detection utilities for MySQL Connector/Python.

Provides a scikit-learn compatible wrapper using HeatWave to score anomalies.
"""
from typing import Optional, Union

import numpy as np
import pandas as pd
from sklearn.base import OutlierMixin

from mysql.ai.ml.base import MyBaseMLModel
from mysql.ai.ml.model import ML_TASK
from mysql.ai.utils import copy_dict

from mysql.connector.abstracts import MySQLConnectionAbstract

EPS = 1e-5


def _get_logits(prob: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Compute logit (logodds) for a probability, clipping to avoid numerical overflow.

    Args:
        prob: Scalar or array of probability values in (0,1).

    Returns:
        logit-transformed probabilities.
    """
    result = np.clip(prob, EPS, 1 - EPS)
    return np.log(result / (1 - result))


class MyAnomalyDetector(MyBaseMLModel, OutlierMixin):
    """
    MySQL HeatWave scikit-learn compatible anomaly/outlier detector.

    Flags samples as outliers when the probability of being an anomaly
    exceeds a user-tunable threshold.
    Includes helpers to obtain decision scores and anomaly probabilities
    for ranking.

    Args:
        db_connection (MySQLConnectionAbstract): Active MySQL DB connection.
        model_name (str, optional): Custom model name in the database.
        fit_extra_options (dict, optional): Extra options for fitting.
        score_extra_options (dict, optional): Extra options for scoring/prediction.

    Attributes:
        boundary: Decision threshold boundary in logit space. Derived from
            trained model's catalog info

    Methods:
        predict(X): Predict outlier/inlier labels.
        score_samples(X): Compute anomaly (normal class) logit scores.
        decision_function(X): Compute signed score above/below threshold for ranking.
    """

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        model_name: Optional[str] = None,
        fit_extra_options: Optional[dict] = None,
        score_extra_options: Optional[dict] = None,
    ):
        """
        Initialize an anomaly detector instance with threshold and extra options.

        Args:
            db_connection: Active MySQL DB connection.
            model_name: Optional model name in DB.
            fit_extra_options: Optional extra fit options.
            score_extra_options: Optional extra scoring options.

        Raises:
            ValueError: If outlier_threshold is not in (0,1).
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        MyBaseMLModel.__init__(
            self,
            db_connection,
            ML_TASK.ANOMALY_DETECTION,
            model_name=model_name,
            fit_extra_options=fit_extra_options,
        )
        self.score_extra_options = copy_dict(score_extra_options)
        self.boundary: Optional[float] = None

    def predict(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
    ) -> np.ndarray:
        """
        Predict outlier/inlier binary labels for input samples.

        Args:
            X: Samples to predict on.

        Returns:
            ndarray: Values are -1 for outliers, +1 for inliers, as per scikit-learn convention.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        return np.where(self.decision_function(X) < 0.0, -1, 1)

    def decision_function(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
    ) -> np.ndarray:
        """
        Compute signed distance to the outlier threshold.

        Args:
            X: Samples to predict on.

        Returns:
            ndarray: Score > 0 means inlier, < 0 means outlier; |value| gives margin.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
            ValueError:
                If the provided model info does not provide threshold
        """
        sample_scores = self.score_samples(X)

        if self.boundary is None:
            model_info = self.get_model_info()
            if model_info is None:
                raise ValueError("Model does not exist in catalog.")

            threshold = model_info["model_metadata"]["training_params"].get(
                "anomaly_detection_threshold", None
            )
            if threshold is None:
                raise ValueError(
                    "Trained model is outdated and does not support threshold. "
                    "Try retraining or using an existing, trained model with MyModel."
                )

            # scikit-learn uses large positive values as inlier
            # and negative as outlier, so we need to flip our threshold
            self.boundary = _get_logits(1.0 - threshold)

        return sample_scores - self.boundary

    def score_samples(
        self,
        X: Union[pd.DataFrame, np.ndarray],  # pylint: disable=invalid-name
    ) -> np.ndarray:
        """
        Compute normal probability logit score for each sample.
        Used for ranking, thresholding.

        Args:
            X: Samples to score.

        Returns:
            ndarray: Logit scores based on "normal" class probability.

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported,
                or if the model is not initialized, i.e., fit or import has not
                been called
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        result = self._model.predict(X, options=self.score_extra_options)

        return _get_logits(
            result["ml_results"]
            .apply(lambda x: x["probabilities"]["normal"])
            .to_numpy()
        )
