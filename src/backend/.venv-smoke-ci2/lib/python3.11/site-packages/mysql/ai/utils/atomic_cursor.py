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

"""Atomic transaction context manager utilities for MySQL Connector/Python.

Provides context manager atomic_transaction() that ensures commit on success
and rollback on error without obscuring the original exception.
"""

from contextlib import contextmanager
from typing import Iterator

from mysql.connector.abstracts import MySQLConnectionAbstract
from mysql.connector.cursor import MySQLCursorAbstract


@contextmanager
def atomic_transaction(
    conn: MySQLConnectionAbstract,
) -> Iterator[MySQLCursorAbstract]:
    """
    Context manager that wraps a MySQL database cursor and ensures transaction
    rollback in case of exception.

    NOTE: DDL statements such as CREATE TABLE cause implicit commits. These cannot
    be managed by a cursor object. Changes made at or before a DDL statement will
    be committed and not rolled back. Callers are responsible for any cleanup of
    this type.

    This class acts as a robust, PEP 343-compliant context manager for handling
    database cursor operations on a MySQL connection. It ensures that all operations
    executed within the context block are part of the same transaction, and
    automatically calls `connection.rollback()` if an exception occurs, helping
    to maintain database integrity. On normal completion (no exception), it simply
    closes the cursor after use. Exceptions are always propagated to the caller.

    Args:
        conn: A MySQLConnectionAbstract instance.
    """
    old_autocommit = conn.autocommit
    cursor = conn.cursor()

    exception_raised = False
    try:
        if old_autocommit:
            conn.autocommit = False

        yield cursor  # provide cursor to block

        conn.commit()
    except Exception:  # pylint: disable=broad-exception-caught
        exception_raised = True
        try:
            conn.rollback()
        except Exception:  # pylint: disable=broad-exception-caught
            # Don't obscure original exception
            pass

        # Raise original exception
        raise
    finally:
        conn.autocommit = old_autocommit

        try:
            cursor.close()
        except Exception:  # pylint: disable=broad-exception-caught
            # don't obscure original exception if exists
            if not exception_raised:
                raise
