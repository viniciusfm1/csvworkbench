from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal
from pydantic import BaseModel, Field, model_validator, field_validator
from enum import Enum

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
    sep : str
        Field separator used to parse ``rows``.
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
    sep: str
    quotechar: str
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


class Severity(str, Enum):
    """Severity levels for diagnostic issues.
 
    Ordered from least to most critical so comparisons like
    ``issue.severity >= Severity.WARNING`` work intuitively.
    """
 
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
 
    def __ge__(self, other: 'Severity') -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.ERROR]
        return order.index(self) >= order.index(other)
 
    def __gt__(self, other: 'Severity') -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.ERROR]
        return order.index(self) > order.index(other)
    

class Issue(BaseModel):
    """A single diagnostic finding inside a csv file.
 
    Parameters
    ----------
    severity : Severity
        How critical the finding is (info / warning / error).
    code : str
        Machine-readable identifier, e.g. ``'column_mismatch'``.
        Used by programmatic consumers and repair strategies.
    line : int or None
        1-based line number where the issue was detected.
        ``None`` means the issue is file-wide (e.g. mixed line endings).
    detail : str
        Human-readable explanation of what was found.
    suggestion : str or None
        Actionable hint for fixing the issue.  Optional.
 
    Examples
    --------
    >>> issue = Issue(
    ...     severity=Severity.ERROR,
    ...     code='column_mismatch',
    ...     line=42,
    ...     detail='expected 5 columns, got 3',
    ...     suggestion='Check for unescaped delimiters near line 42.',
    ... )
    >>> issue.severity >= Severity.WARNING
    True
    """
 
    severity: Severity
    code: str = Field(
        min_length=1,
        pattern=r'^[a-z][a-z0-9_]*$',
        description='Snake-case machine-readable identifier.',
        examples=['column_mismatch', 'mixed_line_ending', 'unbalanced_quotes'],
    )
    line: int | None = Field(
        default=None,
        ge=1,
        description='1-based line number; None for file-wide issues.',
    )
    detail: str = Field(min_length=1)
    suggestion: str | None = Field(default=None)
 
    model_config = {'frozen': True}


class DiagnosticReport(BaseModel):
    """Full diagnostic result for a single csv file.
 
    Produced by the core engine and consumed by both the CLI formatters
    and by programmatic callers.  The model is intentionally read-only
    after construction (``frozen=True``) so formatters cannot mutate it.
 
    Parameters
    ----------
    file_path : Path
        Absolute or relative path to the inspected file.
        The string ``'<stdin>'`` is accepted when reading from a pipe.
    encoding : str
        Detected encoding name as returned by ``chardet`` /
        ``charset-normalizer`` (e.g. ``'utf-8'``, ``'latin-1'``).
    encoding_confidence : float
        Detector confidence in [0.0, 1.0].
    delimiter : str
        Single character used as the field separator. :IMPORTANTE: é single mesmo? 
    quotechar : str
        Single character used for quoting fields. :IMPORTANTE: é single mesmo? 
    column_count : int
        Number of columns inferred from the header row.
    row_count : int
        Number of data rows (header excluded).
    issues : list[Issue]
        All findings, ordered by line number (file-wide issues first).
    elapsed_seconds : float
        Wall-clock time spent running the full inspection.

    Examples
    --------
    >>> report = DiagnosticReport(
    ...     file_path=Path('data.csv'),
    ...     encoding='utf-8',
    ...     encoding_confidence=0.99,
    ...     delimiter=';',
    ...     quotechar='"',
    ...     column_count=10,
    ...     row_count=963,
    ...     issues=[],
    ...     elapsed_seconds=0.726,
    ... )
    >>> report.error_count
    0
    >>> report.has_errors
    False
    """

    file_path: Path | Literal['<stdin>']
    encoding: str = Field(min_length=1)
    encoding_confidence: float = Field(ge=0.0, le=1.0)
    delimiter: str = Field(min_length=1, max_length=1)
    quotechar: str = Field(min_length=1, max_length=1)
    column_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    issues: list[Issue] = Field(default_factory=list)
    elapsed_seconds: float = Field(ge=0.0)
 
    model_config = {'frozen': True}

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator('encoding') # :IMPORTANTE: incluir aqui a formatacao utf_8 -> utf-8 ?
    @classmethod
    def _normalise_encoding(cls, v: str) -> str:
        """Lowercase and strip encoding names for consistent comparisons."""
        return v.strip().lower()
 
    @model_validator(mode='after')
    def _issues_sorted(self) -> 'DiagnosticReport':
        """Guarantee issues are ordered: file-wide first, then by line."""
        object.__setattr__(
            self,
            'issues',
            sorted(
                self.issues,
                key=lambda i: (i.line is not None, i.line or 0),
            ),
        )
        return self
 
    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
 
    @property
    def error_count(self) -> int:
        """Number of issues with severity ERROR."""
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)
 
    @property
    def warning_count(self) -> int:
        """Number of issues with severity WARNING."""
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)
 
    @property
    def has_errors(self) -> bool:
        """True when at least one ERROR-level issue exists."""
        return self.error_count > 0
 
    @property
    def has_warnings(self) -> bool:
        """True when at least one WARNING-level issue exists."""
        return self.warning_count > 0
 
    @property
    def display_path(self) -> str:
        """Path as a string suitable for display in CLI output."""
        if self.file_path == '<stdin>':
            return '<stdin>'
        return str(self.file_path)