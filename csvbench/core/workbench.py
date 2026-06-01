from __future__ import annotations

from pathlib import Path
import time
from typing import TYPE_CHECKING

from csvbench.core.detectors import (
    DelimiterDetector, 
    EncodingDetector, 
    TextDelimiterDetector
)
from csvbench.core.parser import RecordSplitter, FieldSplitter
from csvbench.core.models import CSVFile, DiagnosticReport, Issue, Severity

if TYPE_CHECKING:
    import pandas as pd


class CsvWorkbench:
    """
    Read, inspect, transform, and write CSV files.

    Parameters
    ----------
    path : Path or str
        Path to the source CSV file.

    Examples
    --------
    >>> cf = CsvWorkbench('data.csv').read()
    >>> cf.data.headers
    ['id', 'name', 'city']
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._data: CSVFile | None = None
        self._encoding_detector = EncodingDetector()
        self._delimiter_detector = DelimiterDetector()
        self._quotechar_detector = TextDelimiterDetector()

    def read(
        self,
        sep: str | None = None,
        encoding: str | None = None,
        quotechar: str | None = None,
    ) -> 'CsvWorkbench':
        """
        Read and parse the source file.

        Encoding and separator are inferred automatically when not supplied.
        Pass either argument explicitly to skip detection and override the
        inferred value.

        Parameters
        ----------
        sep : str, optional
            Field separator. When ``None`` (default) the separator is
            inferred automatically by :class:`DelimiterDetector`.
            Accepts any string, including multi-character values
            such as ``'||'`` or ``' | '``.
        encoding : str, optional
            File encoding. When ``None`` (default) the encoding is
            inferred automatically by :class:`EncodingDetector`.
        quotechar : str, optional
            Character used to quote fields containing the separator
            or a newline.

        Returns
        -------
        CsvWorkbench
            The same instance, enabling method chaining.

        Raises
        ------
        FileNotFoundError
            If the source file does not exist.

        Examples
        --------
        >>> cf = CsvWorkbench('data.csv').read()
        >>> cf = CsvWorkbench('data.csv').read(sep=';', encoding='latin-1')
        """
        if not self._path.exists():
            raise FileNotFoundError(self._path)

        encoding_result = (
            self._encoding_detector.detect(self._path).name
            if encoding is None
            else encoding
        )

        delimiter_result = (
            self._delimiter_detector.detect(
                path=self._path,
                encoding_result=encoding_result,
            ).sep
            if sep is None
            else sep
        )

        quotechar_result = (
            self._quotechar_detector.detect(
                path=self._path,
                encoding_result=encoding_result,
                sep=delimiter_result
            ).detected
            if quotechar is None
            else quotechar
        )

        headers, rows = self._parse(
            encoding=encoding_result,
            sep=delimiter_result,
            quotechar=quotechar_result,
        )

        self._data = CSVFile(
            path=self._path.resolve(),
            encoding=encoding_result,
            encoding_confidence=0.0, # resolver: é necessário aqui/agora ?
            sep=delimiter_result,
            quotechar=quotechar_result,
            headers=headers,
            rows=rows,
        )

        return self
    
    def _parse(
        self,
        encoding: str,
        sep: str,
        quotechar: str,
    ) -> tuple[list[str], list[list[str]]]:
        """
        Read the source file and split its contents into headers and rows.

        Handles both single-character and multi-character separators using
        the same code path. Quoted fields are fully supported, a separator
        inside a quoted field is treated as a literal character, and a
        doubled ``quotechar`` inside a quoted field is treated as an escaped
        quote.

        Parameters
        ----------
        encoding : str
            Encoding used to decode the file.
        sep : str
            Field separator. Any string is accepted, including
            multi-character values such as ``'||'`` or ``' | '``.
        quotechar : str
            Character used to quote fields.

        Returns
        -------
        tuple of (list of str, list of list of str)
            A two-element tuple where the first element is the list of
            header names and the second is the list of data rows. Each
            data row is a list of field values with the same length as
            the headers list.

        Raises
        ------
        ValueError
            If the file is empty or contains no non-empty lines.
        """
        text = self._path.read_text(encoding=encoding, errors='surrogateescape') # oq e pra que surrogateescape

        record_splitter = RecordSplitter(quotechar=quotechar)
        field_splitter = FieldSplitter(sep=sep, quotechar=quotechar)
        
        parsed_records = [
            field_splitter.split(record)
            for record in record_splitter.split(text)
        ]

        if not parsed_records:
            raise ValueError(f'File {self._path} is empty.')
        
        return parsed_records[0], parsed_records[1:]

    def run_inspect(self) -> DiagnosticReport:
        """Inspect the parsed file and return a structured diagnostic report.
    
        Must be called after :meth:`read`.  Runs all built-in checks against
        the in-memory :class:`~csvbench.core.models.CSVFile` and assembles
        the results into a :class:`~csvbench.core.models.DiagnosticReport`.
    
        Returns
        -------
        DiagnosticReport
            Immutable report with encoding metadata, shape information, and
            every :class:`~csvbench.core.models.Issue` found.
    
        Raises
        ------
        RuntimeError
            If called before :meth:`read`.
    
        Examples
        --------
        >>> report = CsvWorkbench('data.csv').read().run_inspect()
        >>> report.has_errors
        False
        >>> report.warning_count
        1
        """

        self._require_data()
        start = time.perf_counter()
        issues: list[Issue] = []

        issues.extend(self._check_empty_file())
        issues.extend(self._check_empty_headers())
        issues.extend(self._check_duplicate_headers())
        issues.extend(self._check_column_mismatch())
        issues.extend(self._check_low_encoding_confidence())

        elapsed = time.perf_counter() - start

        return DiagnosticReport(
            file_path=self.data.path,
            encoding=self.data.encoding,
            encoding_confidence=self.data.encoding_confidence,
            delimiter=self.data.sep,
            quotechar=self.data.quotechar,
            column_count=len(self.data.headers),
            row_count=self.data.data_row_count,
            issues=issues,
            elapsed_seconds=elapsed
        )
    
    def _check_empty_file(self) -> list[Issue]:
        """Return an error if the file has no data rows at all.
    
        An empty header row (zero columns) is also caught here, because
        a file with no headers cannot have meaningful data.
    
        Returns
        -------
        list[Issue]
            A single WARNING issue, or an empty list when the file is not empty.
        """

        if self._data.data_row_count == 0:
            return [
                Issue(
                    severity=Severity.WARNING,
                    code='empty_file',
                    line=None,
                    detail='The file contains no data rows.',
                    suggestion='Verify that the file is not empty or '
                            'that the correct delimiter was used.',
                )
            ]
        return []
    
    def _check_empty_headers(self) -> list[Issue]:
        """Return one ERROR per column whose header name is blank.
    
        A blank header (empty string or whitespace-only) is an error
        because it makes column references ambiguous for both human
        readers and downstream tooling.
    
        Returns
        -------
        list[Issue]
            One ERROR issue per blank header found, keyed to line 1.
            Empty list when all headers are non-blank.
        """
        issues: list[Issue] = []
        for idx, header in enumerate(self._data.headers):
            if not header.strip():
                issues.append(
                    Issue(
                        severity=Severity.ERROR,
                        code='empty_header',
                        line=1,
                        detail=f'Column {idx + 1} has no name (blank header).',
                        suggestion='Assign a descriptive name to every column '
                                'in the header row.',
                    )
                )
        return issues
    
    def _check_duplicate_headers(self) -> list[Issue]:
        """Return one WARNING per header name that appears more than once.
    
        Duplicate column names cause silent data loss when converted to
        a DataFrame or dictionary, because the second column silently
        overwrites the first.
    
        Returns
        -------
        list[Issue]
            One WARNING per duplicated name (first occurrence is skipped;
            each subsequent occurrence produces its own issue).
            Empty list when all headers are unique.
        """
        seen: dict[str, int] = {}
        issues: list[Issue] = []
    
        for idx, header in enumerate(self._data.headers):
            normalised = header.strip().lower()
            if normalised in seen:
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        code='duplicate_header',
                        line=1,
                        detail=(
                            f'Column name {header!r} at position {idx + 1} '
                            f'duplicates position {seen[normalised] + 1}.'
                        ),
                        suggestion='Rename duplicate columns to avoid silent '
                                'data loss when converting to DataFrame.',
                    )
                )
            else:
                seen[normalised] = idx
    
        return issues
    
    def _check_column_mismatch(self) -> list[Issue]:
        """Return one ERROR per data row whose field count differs from the header.
    
        Both under-populated rows (too few fields) and over-populated rows
        (too many fields) are reported.  Line numbers are 1-based and
        account for the header row, so the first data row is line 2.
    
        Returns
        -------
        list[Issue]
            One ERROR per offending row.  Empty list when every row matches
            the header width.
        """
        expected = len(self._data.headers)
        issues: list[Issue] = []
    
        for row_idx, row in enumerate(self._data.rows):
            got = len(row)
            if got != expected:
                line = row_idx + 2  # +1 for 0-index, +1 for header row
                issues.append(
                    Issue(
                        severity=Severity.ERROR,
                        code='column_mismatch',
                        line=line,
                        detail=(
                            f'Expected {expected} '
                            f'{"column" if expected == 1 else "columns"}, '
                            f'got {got}.'
                        ),
                        suggestion=(
                            'Check for unescaped delimiters or missing fields '
                            f'near line {line}.'
                        ),
                    )
                )
    
        return issues
 
    def _check_low_encoding_confidence(self) -> list[Issue]:
        """Return a WARNING when the encoding detector confidence is below 0.70.
    
        A low confidence score means the encoding was guessed with limited
        evidence.  Reading the file with the wrong encoding produces silent
        data corruption (mojibake) rather than an explicit error.
    
        Returns
        -------
        list[Issue]
            A single WARNING issue, or an empty list when confidence >= 0.70.
        """
        _THRESHOLD = 0.70
    
        if self._data.encoding_confidence < _THRESHOLD:
            pct = self._data.encoding_confidence * 100
            return [
                Issue(
                    severity=Severity.WARNING,
                    code='low_encoding_confidence',
                    line=None,
                    detail=(
                        f'Encoding detected as {self._data.encoding!r} '
                        f'with only {pct:.0f}% confidence.'
                    ),
                    suggestion=(
                        'Re-open the file with an explicit encoding '
                        '(e.g. latin-1 or utf-8) to rule out mojibake.'
                    ),
                )
            ]
        return []
    
    @property
    def data(self) -> CSVFile:
        """
        The :class:`CSVFile` produced by :meth:`read`.

        Returns
        -------
        CSVFile
            In-memory representation of the parsed file.

        Raises
        ------
        RuntimeError
            If accessed before :meth:`read` is called.

        Examples
        --------
        >>> cf = CsvWorkbench('data.csv').read()
        >>> cf.data.headers
        ['id', 'name', 'city']
        """
        self._require_data()
        return self._data

    def _require_data(self) -> None:
        if self._data is None:
            raise RuntimeError(
                'No data loaded. Call .read() before accessing this.'
            )
        
    def to_pandas(self) -> 'pd.DataFrame':
        """
        Shortcut for ``self.data.to_pandas()``.

        Returns
        -------
        pd.DataFrame
            See :meth:`CSVFile.to_pandas` for full documentation.
        """
        return self.data.to_pandas()

def csvbench(path: Path | str, /) -> CsvWorkbench:
    """Construct a :class:`CsvWorkbench` instance from a file path.
    
    Parameters
    ----------
    path : Path or str
        Path to the source CSV file.
    
    Returns
    -------
    CsvWorkbench
        Uninitialised instance. Chain ``.read()`` to parse the file.
    
    Examples
    --------
    >>> from csvbench import csvbench
    >>> cf = csvbench('data.csv').read()
    >>> cf.data.headers
    ['id', 'name', 'city']
    """
    return CsvWorkbench(path)

def read(
    path: Path | str,
    /,
    sep: str | None = None,
    encoding: str | None = None,
    quotechar: str | None = None,
) -> CsvWorkbench:
    """Construct a :class:`CsvWorkbench` instance and immediately read *path*.
    
    Single-call alternative to ``CsvWorkbench(path).read()``.
    
    Parameters
    ----------
    path : Path or str
        Path to the source CSV file.
    sep : str, optional
        Field separator. Inferred automatically when omitted.
    encoding : str, optional
        File encoding. Inferred automatically when omitted.
    quotechar : str, optional
        Quote character. Inferred automatically when omitted.
    
    Returns
    -------
    CsvWorkbench
        Fully initialised instance with :attr:`~CsvWorkbench.data` populated.
    
    Examples
    --------
    >>> import csvbench
    >>> cf = csvbench.read('data.csv')
    >>> cf = csvbench.read('legacy.csv', sep=';', encoding='latin-1')
    """
    return CsvWorkbench(path).read(sep=sep, encoding=encoding, quotechar=quotechar)