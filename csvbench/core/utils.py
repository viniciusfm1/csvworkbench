from __future__ import annotations

from itertools import islice
from pathlib import Path

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