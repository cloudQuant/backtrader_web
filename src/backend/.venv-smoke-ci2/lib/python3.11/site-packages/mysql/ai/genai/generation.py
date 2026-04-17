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

"""GenAI LLM integration utilities for MySQL Connector/Python.

Provides MyLLM wrapper that issues ML_GENERATE calls via SQL.
"""

import json

from typing import Any, List, Optional

try:
    from langchain_core.language_models.llms import LLM
except ImportError:
    from langchain.llms.base import LLM
from pydantic import PrivateAttr

from mysql.ai.utils import atomic_transaction, execute_sql, format_value_sql
from mysql.connector.abstracts import MySQLConnectionAbstract


class MyLLM(LLM):
    """
    Custom Large Language Model (LLM) interface for MySQL HeatWave.

    This class wraps the generation functionality provided by HeatWave LLMs,
    exposing an interface compatible with common LLM APIs for text generation.
    It provides full support for generative queries and limited support for
    agentic queries.

    Attributes:
        _db_connection (MySQLConnectionAbstract):
            Underlying MySQL connector database connection.
    """

    _db_connection: MySQLConnectionAbstract = PrivateAttr()

    class Config:
        """
        Pydantic config for the model.

        By default, LangChain (through Pydantic BaseModel) does not allow
        setting or storing undeclared attributes such as _db_connection.
        Setting extra = "allow" makes it possible to store extra attributes
        on the class instance, which is required for MyLLM.
        """

        extra = "allow"

    def __init__(self, db_connection: MySQLConnectionAbstract):
        """
        Initialize the MyLLM instance with an active MySQL database connection.

        Args:
            db_connection: A MySQL connection object used to run LLM queries.

        Notes:
            The db_connection is stored as a private attribute via object.__setattr__,
            which is compatible with Pydantic models.
        """
        super().__init__()

        self._db_connection = db_connection

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate a text completion from the LLM for a given input prompt.

        References:
            https://dev.mysql.com/doc/heatwave/en/mys-hwgenai-ml-generate.html
                A full list of supported options (specified by kwargs) can be found under "options"

        Args:
            prompt: The input prompt string for the language model.
            stop: Optional list of stop strings to support agentic and chain-of-thought
                  reasoning workflows.
            **kwargs: Additional keyword arguments providing generation options to
                      the LLM (these are serialized to JSON and passed to the HeatWave syscall).

        Returns:
            The generated model output as a string.
            (The actual completion does NOT include the input prompt.)

        Raises:
            DatabaseError:
                If provided options are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Implementation Notes:
            - Serializes kwargs into a SQL-compatible JSON string.
            - Calls the LLM stored procedure using a database cursor context.
            - Uses `sys.ML_GENERATE` on the server to produce the model output.
            - Expects the server response to be a JSON object with a 'text' key.
        """
        options = kwargs.copy()
        if stop is not None:
            options["stop_sequences"] = stop

        options_placeholder, options_params = format_value_sql(options)
        with atomic_transaction(self._db_connection) as cursor:
            # The prompt is passed as a parameterized argument (avoids SQL injection).
            generate_query = f"""SELECT sys.ML_GENERATE("%s", {options_placeholder});"""
            execute_sql(cursor, generate_query, params=(prompt, *options_params))
            # Expect a JSON-encoded result from MySQL; parse to extract the output.
            llm_response = json.loads(cursor.fetchone()[0])["text"]

        return llm_response

    @property
    def _identifying_params(self) -> dict:
        """
        Return a dictionary of params that uniquely identify this LLM instance.

        Returns:
            dict: Dictionary of identifier parameters (should include
                model_name for tracing/caching).
        """
        return {
            "model_name": "mysql_heatwave_llm",
        }

    @property
    def _llm_type(self) -> str:
        """
        Get the type name of this LLM implementation.

        Returns:
            A string identifying the LLM provider (used for logging or metrics).
        """
        return "mysql_heatwave_llm"
