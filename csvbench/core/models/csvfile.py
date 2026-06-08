from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from pydantic import AliasChoices, BaseModel, Field, model_validator

if TYPE_CHECKING:
    import pandas as pd

class CSVFile(BaseModel):
    """
    In-memory representation of a successfully parsed CSV file.

    Parameters
    ----------
    path : Path
        Absolute path to the source file.
    encoding : str
        Encoding used when the file was read.
    encoding_confidence : float
        Confidence score of the encoding detection.
    delimiter : str
        Field separator used to parse ``rows``.
    delimiter_confidence : float
        Confidence score of the delimiter detection.
    delimiter_method : str
        Method used to detect the delimiter.
    quotechar : str
        Quote character recognised during parsing.
    headers : list of str
        Column names extracted from the first non-empty row.
    rows : list of list of str
        Data rows, excluding the header row.
    row_count : int
        Number of data rows. Computed automatically.

    Examples
    --------
    >>> csv_file.headers
    ['id', 'name', 'city']
    >>> csv_file.row_count
    42
    """

    path: Path
    
    encoding: str
    encoding_confidence: float = Field(ge=0.0, le=1.0)
    encoding_method: str
    
    delimiter: str = Field(validation_alias=AliasChoices('delimiter', 'sep'))
    delimiter_confidence: float = Field(ge=0.0, le=1.0)
    delimiter_method: str
    
    quotechar: str | None
    quotechar_confidence: float = Field(ge=0.0, le=1.0)
    quotechar_method: str
    
    headers: list[str]
    rows: list[list[str]]
    data_row_count: int = 0

    @model_validator(mode='after')
    def _set_data_row_count(self) -> 'CSVFile':
        self.data_row_count = len(self.rows)
        return self
    
    def to_pandas(self) -> 'pd.DataFrame':
        """
        Convert to a :class:`pandas.DataFrame`.

        pandas is an optional dependency. Install it with::

            pip install csvbench[pandas]

        Returns
        -------
        pd.DataFrame
            DataFrame with column names from ``headers`` and
            data from ``rows``. All values are ``str`` — cast
            downstream as needed.

        Raises
        ------
        ImportError
            If pandas is not installed.

        Examples
        --------
        >>> df = csv_file.to_pandas()
        >>> df.shape
        (42, 3)
        >>> df.dtypes
        id      object
        name    object
        city    object
        dtype: object
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                'pandas is required for to_pandas(). '
                'Install it with: pip install csvbench[pandas]'
            ) from exc

        return pd.DataFrame(self.rows, columns=self.headers)
    
    def write(self, path: Path | str, delimiter: str | None = None, quotechar: str | None = None) -> None:
        """Serialize the CSV file to disk.

        Parameters
        ----------
        path : Path or str
            Destination path for the output file.
        delimiter : str, optional
            Field separator to use. Defaults to the detected delimiter.
        quotechar : str, optional
            Quote character to use. Defaults to the detected quotechar,
            falling back to ``"`` if none was detected.
        """
        effective_delimiter = delimiter or self.delimiter
        effective_quotechar = quotechar or self.quotechar or '"'

        lines = [
            self._serialize_row(self.headers, effective_delimiter, effective_quotechar),
            *[
                self._serialize_row(row, effective_delimiter, effective_quotechar)
                for row in self.rows
            ],
        ]

        Path(path).write_text('\n'.join(lines), encoding=self.encoding)

    def _serialize_row(self, row: list[str], delimiter: str, quotechar: str) -> str:
        return delimiter.join(
            self._serialize_field(field, delimiter, quotechar)
            for field in row
        )

    @staticmethod
    def _serialize_field(field: str, delimiter: str, quotechar: str) -> str:
        needs_quoting = (
            delimiter in field
            or quotechar in field
            or '\n' in field
            or '\r' in field
        )

        if not needs_quoting:
            return field

        escaped = field.replace(quotechar, quotechar * 2)
        return f'{quotechar}{escaped}{quotechar}'