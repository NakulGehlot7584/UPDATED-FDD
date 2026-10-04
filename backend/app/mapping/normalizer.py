import re


def normalize_column_name(column_name: str) -> str:
    """
    Normalize a CSV column name into a consistent token-friendly form.

    This function changes formatting only.
    It does not assign a semantic role.
    """

    if not isinstance(column_name, str):
        raise TypeError("column_name must be a string")

    name = column_name.strip()

    # Split camelCase / PascalCase transitions (e.g. supplyAirTemp -> supply_Air_Temp)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)

    name = name.lower()

    # Treat common separators and bracket delimiters as equivalent token boundaries
    name = re.sub(r"[\s\-\(\)\[\]\{\}\.\/]+", "_", name)

    # Keep letters, numbers, and underscores.
    name = re.sub(r"[^a-z0-9_]", "", name)

    # Collapse repeated underscores.
    name = re.sub(r"_+", "_", name)

    # Remove leading/trailing underscores.
    name = name.strip("_")

    return name
