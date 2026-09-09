from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import database_path


PUBLIC_TABLES = {
    "users",
    "events",
    "dataset_manifest",
    "incident_catalog",
}

FORBIDDEN_SQL = re.compile(
    r"\b(attach|detach|alter|analyze|create|delete|drop|insert|load_extension|pragma|reindex|replace|update|vacuum)\b",
    re.IGNORECASE,
)
COMMENT_PATTERN = re.compile(r"--|/\*|\*/")


class QueryRejected(ValueError):
    """Raised when a query violates the read-only execution policy."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float
    executed_sql: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "executed_sql": self.executed_sql,
        }


def _mask_quoted_segments(statement: str) -> str:
    """Blank SQL strings and quoted identifiers while preserving character offsets."""
    masked = list(statement)
    closing_delimiters = {"'": "'", '"': '"', "`": "`", "[": "]"}
    index = 0
    while index < len(statement):
        opener = statement[index]
        closing = closing_delimiters.get(opener)
        if closing is None:
            index += 1
            continue

        masked[index] = " "
        index += 1
        while index < len(statement):
            masked[index] = " "
            if statement[index] == closing:
                if opener != "[" and index + 1 < len(statement) and statement[index + 1] == closing:
                    masked[index + 1] = " "
                    index += 2
                    continue
                index += 1
                break
            index += 1
        else:
            raise QueryRejected("SQL contains an unterminated quoted value or identifier.")

    return "".join(masked)


def _readonly_authorizer(action: int, arg1: str | None, _arg2: str | None, _db: str | None, _source: str | None) -> int:
    denied_actions = {
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
    }
    if action in denied_actions:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and arg1 and arg1.lower() not in PUBLIC_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def validate_readonly_sql(sql: str, row_limit: int = 200) -> str:
    """Validate without rewriting SQL; execute_readonly bounds returned rows."""
    if not isinstance(sql, str) or not sql.strip():
        raise QueryRejected("SQL must be a non-empty string.")
    statement = sql.strip()
    executable_sql = _mask_quoted_segments(statement)
    if ";" in executable_sql:
        raise QueryRejected("Multiple statements and semicolons are not allowed.")
    if COMMENT_PATTERN.search(executable_sql):
        raise QueryRejected("SQL comments are not allowed.")
    if FORBIDDEN_SQL.search(executable_sql):
        raise QueryRejected("Only read-only SELECT/CTE queries are allowed.")
    if not re.match(r"^(select|with)\b", executable_sql, re.IGNORECASE):
        raise QueryRejected("Query must begin with SELECT or WITH.")
    if row_limit < 1 or row_limit > 500:
        raise QueryRejected("row_limit must be between 1 and 500.")

    return statement


def connect_readonly(path: Path | None = None) -> sqlite3.Connection:
    selected = (path or database_path()).resolve()
    if not selected.exists():
        raise FileNotFoundError(f"Analytics database not found: {selected}")
    connection = sqlite3.connect(f"file:{selected.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 1000")
    connection.set_authorizer(_readonly_authorizer)
    return connection


def execute_readonly(
    sql: str,
    parameters: Iterable[Any] | None = None,
    *,
    row_limit: int = 200,
    timeout_ms: int = 2000,
    path: Path | None = None,
) -> QueryResult:
    if timeout_ms < 50 or timeout_ms > 10_000:
        raise QueryRejected("timeout_ms must be between 50 and 10000.")
    guarded_sql = validate_readonly_sql(sql, row_limit=row_limit)
    started = time.perf_counter()
    deadline = started + timeout_ms / 1000

    with closing(connect_readonly(path)) as connection:
        def progress() -> int:
            return 1 if time.perf_counter() > deadline else 0

        connection.set_progress_handler(progress, 1000)
        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute(guarded_sql, tuple(parameters or ()))
                # Bound the output, not inner LIMITs that define the analysis cohort.
                fetched = cursor.fetchmany(row_limit + 1)
                columns = [item[0] for item in (cursor.description or [])]
        except sqlite3.DatabaseError as exc:
            message = "Query timed out." if "interrupted" in str(exc).lower() else f"Query rejected by SQLite policy: {exc}"
            raise QueryRejected(message) from exc
        finally:
            connection.set_progress_handler(None, 0)

    truncated = len(fetched) > row_limit
    visible = fetched[:row_limit]
    rows = [{column: row[column] for column in columns} for row in visible]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return QueryResult(columns, rows, len(rows), truncated, elapsed_ms, guarded_sql)
