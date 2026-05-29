from __future__ import annotations

from pathlib import Path
import re
from typing import TYPE_CHECKING, Iterator

from csvbench.core.detectors import (
    DelimiterDetector, 
    EncodingDetector, 
    TextDelimiterDetector
)
from csvbench.core.parser import RecordSplitter, FieldSplitter
from csvbench.core.models import CSVFile

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