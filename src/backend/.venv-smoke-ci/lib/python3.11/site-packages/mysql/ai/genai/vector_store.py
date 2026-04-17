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

"""MySQL-backed vector store for embeddings and semantic document retrieval.

Provides a VectorStore implementation persisting documents, metadata, and
embeddings in MySQL, plus similarity search utilities.
"""

import json

from typing import Any, Iterable, List, Optional, Sequence, Union

import pandas as pd

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from pydantic import PrivateAttr

from mysql.ai.genai.embedding import MyEmbeddings
from mysql.ai.utils import (
    VAR_NAME_SPACE,
    atomic_transaction,
    delete_sql_table,
    execute_sql,
    extend_sql_table,
    format_value_sql,
    get_random_name,
    is_table_empty,
    source_schema,
    table_exists,
)
from mysql.connector.abstracts import MySQLConnectionAbstract

BASIC_EMBEDDING_QUERY = "Hello world!"
EMBEDDING_SOURCE = "external_source"

VAR_EMBEDDING = f"{VAR_NAME_SPACE}.embedding"
VAR_CONTEXT = f"{VAR_NAME_SPACE}.context"
VAR_CONTEXT_MAP = f"{VAR_NAME_SPACE}.context_map"
VAR_RETRIEVAL_INFO = f"{VAR_NAME_SPACE}.retrieval_info"
VAR_OPTIONS = f"{VAR_NAME_SPACE}.options"

ID_SPACE = "internal_ai_id_"


class MyVectorStore(VectorStore):
    """
    MySQL-backed vector store for handling embeddings and semantic document retrieval.

    Supports adding, deleting, and searching high-dimensional vector representations
    of documents using efficient storage and HeatWave ML similarity search procedures.

    Supports use as a context manager: when used in a `with` statement, all backing
    tables/data are deleted automatically when the block exits (even on exception).

    Attributes:
        db_connection (MySQLConnectionAbstract): Active MySQL database connection.
        embedder (Embeddings): Embeddings generator for computing vector representations.
        schema_name (str): SQL schema for table storage.
        table_name (Optional[str]): Name of the active table backing the store
            (or None until created).
        embedding_dimension (int): Size of embedding vectors stored.
        next_id (int): Internal counter for unique document ID generation.
    """

    _db_connection: MySQLConnectionAbstract = PrivateAttr()
    _embedder: Embeddings = PrivateAttr()
    _schema_name: str = PrivateAttr()
    _table_name: Optional[str] = PrivateAttr()
    _embedding_dimension: int = PrivateAttr()
    _next_id: int = PrivateAttr()

    def __init__(
        self,
        db_connection: MySQLConnectionAbstract,
        embedder: Optional[Embeddings] = None,
    ) -> None:
        """
        Initialize a MyVectorStore with a database connection and embedding generator.

        Args:
            db_connection: MySQL database connection for all vector operations.
            embedder: Embeddings generator used for creating and querying embeddings.

        Raises:
            ValueError: If the schema name is not valid
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        super().__init__()
        self._next_id = 0

        self._schema_name = source_schema(db_connection)
        self._embedder = embedder or MyEmbeddings(db_connection)
        self._db_connection = db_connection
        self._table_name: Optional[str] = None

        # Embedding dimension determined using an example call.
        # Assumes embeddings have fixed length.
        self._embedding_dimension = len(
            self._embedder.embed_query(BASIC_EMBEDDING_QUERY)
        )

    def _get_ids(self, num_ids: int) -> list[str]:
        """
        Generate a batch of unique internal document IDs for vector storage.

        Args:
            num_ids: Number of IDs to create.

        Returns:
            List of sequentially numbered internal string IDs.
        """
        ids = [
            f"internal_ai_id_{i}" for i in range(self._next_id, self._next_id + num_ids)
        ]
        self._next_id += num_ids
        return ids

    def _make_vector_store(self) -> None:
        """
        Create a backing SQL table for storing vectors if not already created.

        Returns:
            None

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            The table name is randomized to avoid collisions.
            Schema includes content, metadata, and embedding vector.
        """
        if self._table_name is None:
            with atomic_transaction(self._db_connection) as cursor:
                table_name = get_random_name(
                    lambda table_name: not table_exists(
                        cursor, self._schema_name, table_name
                    )
                )

                create_table_stmt = f"""
                CREATE TABLE {self._schema_name}.{table_name} (
                    `id` VARCHAR(128) NOT NULL,
                    `content` TEXT,
                    `metadata` JSON DEFAULT NULL,
                    `embed` vector(%s),
                    PRIMARY KEY (`id`)
                ) ENGINE=InnoDB;
                """
                execute_sql(
                    cursor, create_table_stmt, params=(self._embedding_dimension,)
                )

                self._table_name = table_name

    def delete(self, ids: Optional[Sequence[str]] = None, **_: Any) -> None:
        """
        Delete documents by ID. Optionally deletes the vector table if empty after deletions.

        Args:
            ids: Optional sequence of document IDs to delete. If None, no action is taken.

        Returns:
            None

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            If the backing table is empty after deletions, the table is dropped and
            table_name is set to None.
        """
        with atomic_transaction(self._db_connection) as cursor:
            if ids:
                for _id in ids:
                    execute_sql(
                        cursor,
                        f"DELETE FROM {self._schema_name}.{self._table_name} WHERE id = %s",
                        params=(_id,),
                    )

            if is_table_empty(cursor, self._schema_name, self._table_name):
                self.delete_all()

    def delete_all(self) -> None:
        """
        Delete and drop the entire vector store table.

        Returns:
            None
        """
        if self._table_name is not None:
            with atomic_transaction(self._db_connection) as cursor:
                delete_sql_table(cursor, self._schema_name, self._table_name)
                self._table_name = None

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[list[dict]] = None,
        ids: Optional[List[str]] = None,
        **_: dict,
    ) -> List[str]:
        """
        Add a batch of text strings and corresponding metadata to the vector store.

        Args:
            texts: List of strings to embed and store.
            metadatas: Optional list of metadata dicts (one per text).
            ids: Optional custom document IDs.

        Returns:
            List of document IDs corresponding to the added texts.

        Raises:
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            If metadatas is None, an empty dict is assigned to each document.
        """
        texts = list(texts)

        documents = [
            Document(page_content=text, metadata=meta)
            for text, meta in zip(texts, metadatas or [{}] * len(texts))
        ]
        return self.add_documents(documents, ids=ids)

    @classmethod
    def from_texts(
        cls,
        texts: Iterable[str],
        embedder: Embeddings,
        metadatas: Optional[list[dict]] = None,
        db_connection: MySQLConnectionAbstract = None,
    ) -> VectorStore:
        """
        Construct and populate a MyVectorStore instance from raw texts and metadata.

        Args:
            texts: List of strings to vectorize and store.
            embedder: Embeddings generator to use.
            metadatas: Optional list of metadata dicts per text.
            db_connection: Active MySQL connection.

        Returns:
            Instance of MyVectorStore containing the added texts.

        Raises:
            ValueError: If db_connection is not provided.
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.
        """
        if db_connection is None:
            raise ValueError(
                "db_connection must be specified to create a MyVectorStore object"
            )

        texts = list(texts)

        instance = cls(db_connection=db_connection, embedder=embedder)
        instance.add_texts(texts, metadatas=metadatas)

        return instance

    def add_documents(
        self, documents: list[Document], ids: list[str] = None
    ) -> list[str]:
        """
        Embed and store Document objects as high-dimensional vectors with metadata.

        Args:
            documents: List of Document objects (each with 'page_content' and 'metadata').
            ids: Optional list of explicit document IDs. Must match the length of documents.

        Returns:
            List of document IDs stored.

        Raises:
            ValueError: If provided IDs do not match the number of documents.
            DatabaseError:
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Notes:
            Automatically creates the backing table if it does not exist.
        """
        if ids and len(ids) != len(documents):
            msg = (
                "ids must be the same length as documents. "
                f"Got {len(ids)} ids and {len(documents)} documents."
            )
            raise ValueError(msg)

        if len(documents) > 0:
            self._make_vector_store()
        else:
            return []

        if ids is None:
            ids = self._get_ids(len(documents))

        content = [doc.page_content for doc in documents]
        vectors = self._embedder.embed_documents(content)

        df = pd.DataFrame()
        df["id"] = ids
        df["content"] = content
        df["embed"] = vectors
        df["metadata"] = [doc.metadata for doc in documents]

        with atomic_transaction(self._db_connection) as cursor:
            extend_sql_table(
                cursor,
                self._schema_name,
                self._table_name,
                df,
                col_name_to_placeholder_string={"embed": "string_to_vector(%s)"},
            )

        return ids

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        **kwargs: Any,
    ) -> list[Document]:
        """
        Search for and return the most similar documents in the store to the given query.

        Args:
            query: String query to embed and use for similarity search.
            k: Number of top documents to return.
            kwargs: options to pass to ML_SIMILARITY_SEARCH. Currently supports
                distance_metric, max_distance, percentage_distance, and segment_overlap

        Returns:
            List of Document objects, ordered from most to least similar.

        Raises:
            DatabaseError:
                If provided kwargs are invalid or unsupported.
                If a database connection issue occurs.
                If an operational error occurs during execution.

        Implementation Notes:
            - Calls ML similarity search within MySQL using stored procedures.
            - Retrieves IDs, content, and metadata for search matches.
            - Parsing and retrieval for context results are handled via intermediate JSONs.
        """
        if self._table_name is None:
            return []

        embedding = self._embedder.embed_query(query)

        with atomic_transaction(self._db_connection) as cursor:
            # Set the embedding variable for the similarity search SP
            execute_sql(
                cursor,
                f"SET @{VAR_EMBEDDING} = string_to_vector(%s)",
                params=[str(embedding)],
            )

            distance_metric = kwargs.get("distance_metric", "COSINE")
            retrieval_options = {
                "max_distance": kwargs.get("max_distance", 0.6),
                "percentage_distance": kwargs.get("percentage_distance", 20.0),
                "segment_overlap": kwargs.get("segment_overlap", 0),
            }

            retrieval_options_placeholder, retrieval_options_params = format_value_sql(
                retrieval_options
            )
            similarity_search_query = f"""
            CALL sys.ML_SIMILARITY_SEARCH(
                @{VAR_EMBEDDING},
                JSON_ARRAY(
                    '{self._schema_name}.{self._table_name}'
                ),
                JSON_OBJECT(
                    "segment", "content",
                    "segment_embedding", "embed",
                    "document_name", "id"
                ),
                {k},
                %s,
                NULL,
                NULL,
                {retrieval_options_placeholder},
                @{VAR_CONTEXT},
                @{VAR_CONTEXT_MAP},
                @{VAR_RETRIEVAL_INFO}
            )
            """

            execute_sql(
                cursor,
                similarity_search_query,
                params=[distance_metric, *retrieval_options_params],
            )
            execute_sql(cursor, f"SELECT @{VAR_CONTEXT_MAP}")

            results = []

            context_maps = json.loads(cursor.fetchone()[0])
            for context in context_maps:
                execute_sql(
                    cursor,
                    (
                        "SELECT id, content, metadata "
                        f"FROM {self._schema_name}.{self._table_name} "
                        "WHERE id = %s"
                    ),
                    params=(context["document_name"],),
                )
                doc_id, content, metadata = cursor.fetchone()

                doc_args = {
                    "id": doc_id,
                    "page_content": content,
                }
                if metadata is not None:
                    doc_args["metadata"] = json.loads(metadata)

                doc = Document(**doc_args)
                results.append(doc)

            return results

    def __enter__(self) -> "VectorStore":
        """
        Enter the runtime context related to this vector store instance.

        Returns:
            The current MyVectorStore object, allowing use within a `with` statement block.

        Usage Notes:
            - Intended for use in a `with` statement to ensure automatic
              cleanup of resources.
            - No special initialization occurs during context entry, but enables
              proper context-managed lifecycle.

        Example:
            with MyVectorStore(db_connection, embedder) as vectorstore:
                vectorstore.add_texts([...])
                # Vector store is active within this block.
            # All storage and resources are now cleaned up.
        """
        return self

    def __exit__(
        self,
        exc_type: Union[type, None],
        exc_val: Union[BaseException, None],
        exc_tb: Union[object, None],
    ) -> None:
        """
        Exit the runtime context for the vector store, ensuring all storage
        resources are cleaned up.

        Args:
            exc_type: The exception type, if any exception occurred in the context block.
            exc_val: The exception value, if any exception occurred in the context block.
            exc_tb:  The traceback object, if any exception occurred in the context block.

        Returns:
            None: Indicates that exceptions are never suppressed; they will propagate as normal.

        Implementation Notes:
            - Automatically deletes all vector store data and backing tables via `delete_all()`
            upon exiting the context.
            - This cleanup occurs whether the block exits normally or due to an exception.
            - Does not suppress exceptions; errors in the context block will continue to propagate.
            - Use when the vector store lifecycle is intended to be temporary or scoped.

        Example:
            with MyVectorStore(db_connection, embedder) as vectorstore:
                vectorstore.add_texts([...])
                # Vector store is active within this block.
            # All storage and resources are now cleaned up.
        """
        self.delete_all()
        # No return, so exceptions are never suppressed
