from pathlib import Path

import polars as pl


def scan_csv(file_path: str | Path) -> dict:
    """
    Inspect a CSV file and return basic structural information.

    The scanner does not perform semantic role mapping.
    Its responsibility is to discover what is inside the CSV.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file, got: {path.suffix}")

    try:
        with path.open("rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                raise ValueError(
                    f"File '{path.name}' is binary or corrupted and is not a valid text CSV."
                )
    except OSError as e:
        raise ValueError(f"Failed to read '{path.name}': {e}")

    df = pl.read_csv(path)
    if df.height == 0:
        raise ValueError(f"CSV file '{path.name}' contains no data rows (empty or header-only).")
    if df.width == 0:
        raise ValueError(f"CSV file '{path.name}' contains no columns.")

    columns = []

    for column_name in df.columns:
        series = df[column_name]

        columns.append(
            {
                "name": column_name,
                "dtype": str(series.dtype),
                "null_count": series.null_count(),
                "sample_values": series.head(5).to_list(),
            }
        )

    return {
        "file_name": path.name,
        "file_path": str(path),
        "row_count": df.height,
        "column_count": df.width,
        "columns": columns,
    }