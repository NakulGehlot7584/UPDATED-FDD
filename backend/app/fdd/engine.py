"""DataFusion SQL engine wrapper for Open-FDD execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import polars as pl
from datafusion import SessionContext


class DataFusionEngine:
    """Wrapper managing Apache DataFusion SessionContext for running FDD SQL rules."""

    def __init__(self, ctx: Optional[SessionContext] = None):
        self.ctx = ctx if ctx is not None else SessionContext()

    def register_parquet_file(self, table_name: str, file_path: Path | str) -> None:
        """Register a single Parquet file as a table."""
        path_str = str(file_path)
        if not Path(path_str).exists():
            raise FileNotFoundError(f"Parquet file not found: {path_str}")
        
        if self.table_exists(table_name):
            self.deregister_table(table_name)
        self.ctx.register_parquet(table_name, path_str)

    def register_parquet_tree(
        self,
        table_name: str,
        root_dir: Path | str,
        partitioning: str = "hive",
    ) -> bool:
        """Register a directory tree of Parquet files with Hive partitioning."""
        root_path = Path(root_dir)
        if not root_path.exists():
            return False

        parquet_files = list(root_path.glob("**/*.parquet"))
        if not parquet_files:
            return False

        if self.table_exists(table_name):
            self.deregister_table(table_name)

        dataset = ds.dataset(str(root_path), format="parquet", partitioning=partitioning)
        self.ctx.register_dataset(table_name, dataset)
        return True

    def register_arrow_table(self, table_name: str, arrow_table: pa.Table) -> None:
        """Register an in-memory PyArrow Table."""
        if self.table_exists(table_name):
            self.deregister_table(table_name)
        
        batches = arrow_table.to_batches()
        if not batches:
            raise ValueError("Arrow table has no record batches to register")
        self.ctx.register_record_batches(table_name, [batches])

    def deregister_table(self, table_name: str) -> None:
        """Deregister a table if present."""
        if self.table_exists(table_name):
            self.ctx.deregister_table(table_name)

    def table_exists(self, table_name: str) -> bool:
        """Check if table is registered in DataFusion."""
        try:
            return self.ctx.table_exist(table_name)
        except Exception:
            # Fallback if table_exist API signature varies
            try:
                self.ctx.table(table_name)
                return True
            except Exception:
                return False

    def get_table_columns(self, table_name: str = "history") -> Set[str]:
        """Get lower-case column names of registered table."""
        try:
            df = self.ctx.table(table_name)
            schema = df.schema()
            return {f.name.lower() for f in schema}
        except Exception:
            return set()

    def query(self, sql: str) -> pa.Table:
        """Execute SQL query and return pyarrow.Table."""
        df = self.ctx.sql(sql)
        batches = df.collect()
        if not batches:
            schema = df.schema()
            # Construct empty pyarrow table with expected schema
            return pa.Table.from_batches([], schema=pa.schema([pa.field(f.name, pa.string()) for f in schema]))
        return pa.Table.from_batches(batches)

    def query_to_polars(self, sql: str) -> pl.DataFrame:
        """Execute SQL query and return polars.DataFrame."""
        arrow_table = self.query(sql)
        return pl.from_arrow(arrow_table)

    def query_to_dicts(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL query and return list of row dictionaries."""
        arrow_table = self.query(sql)
        return arrow_table.to_pylist()


def create_engine() -> DataFusionEngine:
    """Create a new isolated DataFusionEngine instance."""
    return DataFusionEngine()
