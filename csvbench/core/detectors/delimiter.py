from __future__ import annotations

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

from csvbench.core.utils import read_sample


class DelimiterResult(BaseModel):
    """
    Outcome of delimiter detection.

    Parameters
    ----------
    sep : str
        Field separator detected or supplied by the caller.
        Accepts any string, including multi-character values
        such as ``'||'`` or ``' | '``.
    confidence : float
        Detection confidence in the range ``[0.0, 1.0]``.
        Always ``1.0`` when ``method='override'``.
    method : {'sniffed', 'regex', 'override'}
        How the separator was determined.

        ``'sniffed'``
            :class:`csv.Sniffer` produced a candidate that passed
            the column-consistency check.
        ``'regex'``
            Frequency and consistency analysis via regular expressions.
        ``'override'``
            The caller supplied ``sep`` explicitly.

    Examples
    --------
    >>> result = DelimiterResult(sep=';', confidence=0.95, method='sniffed')
    >>> result.sep
    ';'
    """

    sep: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal['sniffed', 'regex', 'override']


class DelimiterDetector:
    def __init__(self, candidates: list[str] | None = None, max_lines: int = 50) -> None:
        self.candidates = candidates
        self.max_lines = max_lines

    def detect(self, path: Path | str, encoding_result: str) -> DelimiterResult:
        """
        Detect the delimiter of *path*.

        Parameters
        ----------
        path : Path or str
            File to inspect.
        encoding_result : EncodingResult
            Encoding previously detected by :class:`EncodingDetector`.
            The ``encoding`` attribute is used to decode the file bytes.

        Returns
        -------
        DelimiterResult
            Detected delimiter with confidence and detection method.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        
        sample = read_sample(path=path, encoding=encoding_result, max_lines=self.max_lines)
        return self._try_sniffer(sample=sample)
    
    def _try_sniffer(self, sample: str) -> DelimiterResult:
        """
        Detect the delimiter by delegating to :class:`DelimiterSniffer`.

        Parameters
        ----------
        sample : str
            Raw text sample returned by :meth:`core.utils.read_sample`.

        Returns
        -------
        DelimiterResult
            Result produced by :class:`DelimiterSniffer` with
            ``method='sniffed'`` and a confidence derived from
            the weighted score.

        Raises
        ------
        ValueError
            If *sample* is empty or contains no non-empty lines.
        """
        from csvbench.core.sniffer import DelimiterSniffer

        return DelimiterSniffer(candidates=self.candidates).sniff(sample)