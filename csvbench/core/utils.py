from __future__ import annotations

from itertools import islice
from pathlib import Path

from csvbench.core.parser.record_splitter import RecordSplitter

_RECORD_SAMPLE_CHUNK_SIZE = 65_536


def read_sample(path: Path | str, encoding: str, max_lines: int = 50) -> str:
        """
        Read the first ``max_lines`` lines of *path* as a single string.

        Parameters
        ----------
        path : Path or str
            File to read.
        encoding : str
            Encoding used to decode the file bytes.
            Decoding errors are replaced with the Unicode replacement
            character rather than raising an exception.

        Returns
        -------
        str
            Concatenation of the first ``max_lines`` lines, preserving
            line endings.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        """
        
        with path.open(encoding=encoding, errors='replace') as fh:
            sample = ''.join(islice(fh, max_lines))
        return sample


def read_record_sample(
    path: Path | str,
    encoding: str,
    max_records: int = 50,
    quotechar: str = '"',
) -> str:
    """
    Read the first ``max_records`` logical CSV records of *path*.

    Physical newlines inside quoted fields do not count as record
    boundaries. Sampling stops after ``max_records`` complete records
    so delimiter sniffing is not skewed by mid-field line breaks.

    Parameters
    ----------
    path : Path or str
        File to read.
    encoding : str
        Encoding used to decode the file bytes.
        Decoding errors are replaced with the Unicode replacement
        character rather than raising an exception.
    max_records : int, default 50
        Maximum number of logical records to return.
    quotechar : str, default ``'"'``
        Quote character used to recognise embedded newlines.
        A default of ``'"'`` is sufficient for delimiter sampling.

    Returns
    -------
    str
        The first ``max_records`` logical records joined by ``\\n``.
        Re-splitting with :class:`RecordSplitter` recovers the same
        records because embedded newlines remain inside quotes.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    path = Path(path)
    splitter = RecordSplitter(quotechar=quotechar, preserve_empty_records=False)
    chunks: list[str] = []

    with path.open(encoding=encoding, errors='replace') as fh:
        while True:
            piece = fh.read(_RECORD_SAMPLE_CHUNK_SIZE)
            eof = not piece
            if piece:
                chunks.append(piece)

            records = [
                record
                for record in splitter.split(''.join(chunks))
                if record.strip()
            ]

            if eof:
                return '\n'.join(records[:max_records])

            complete = records[:-1]
            if len(complete) >= max_records:
                return '\n'.join(complete[:max_records])