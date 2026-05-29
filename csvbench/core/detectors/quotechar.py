from __future__ import annotations

import math
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator, Literal

from pydantic import BaseModel, Field, model_validator

from csvbench.core.utils import read_sample

_QUOTECHAR_CANDIDATES: list[str] = ['"', '\'', '|', '~', ':', '`', '\x07', '\x1c', '\x1f']

_DEFAULT_WEIGHTS: dict[str, float] = {
    'frequency':   0.3,
    'consistency': 0.4,
    'position':    0.3,
}


@dataclass
class _TextDelimiterCandidateScore:
    """
    Intermediate scoring result for a quote character candidate.

    Parameters
    ----------
    char : str
        The quote character being evaluated.
    frequency : float
        Normalised co-occurrence score with the field separator,
        in the range ``[0.0, 1.0]``.
    consistency : float
        Dominance ratio of this candidate over all quoted fields
        found in the sample, in the range ``[0.0, 1.0]``.
    position : float
        Structural position score: fraction of lines where the
        candidate appears at a quoting-relevant position (line
        start/end, immediately before/after the separator),
        in the range ``[0.0, 1.0]``.
    total : float
        Weighted sum of the three scores.
    field_count : int
        Raw count of lines that produced at least one positional
        hit for this candidate. Used for tie-breaking and
        diagnostics.
    """

    char: str
    frequency: float
    consistency: float
    position: float
    total: float
    field_count: int


class TextDelimiterResult(BaseModel):
    """
    Outcome of quote character detection.

    Parameters
    ----------
    detected : str or None
        Dominant quote character found in the file (``'"'``, ``"'"``),
        or ``None`` when no quoted fields were found.
    confidence : float
        Detection confidence in the range ``[0.0, 1.0]``.
        Computed as the weighted total score of the winning candidate,
        normalised against the sum of all candidate totals.
        Always ``0.0`` when ``detected`` is ``None``.
    has_conflict : bool
        ``True`` when more than one distinct quote character was
        found across the file's fields.
    conflict_chars : list of str
        Minority quote characters detected alongside the dominant one.
        Empty list when ``has_conflict`` is ``False``.
    total_quoted_fields : int
        Total number of lines that carried any recognisable quoting
        signal. Used as the denominator for ``confidence``.
    method : {'override', 'detected'}
        ``'override'`` when the caller supplied the quote character
        explicitly; ``'detected'`` when it was inferred from the sample.

    Examples
    --------
    Clean file — every quoted field uses double quotes:

    >>> result = TextDelimiterResult(
    ...     detected='"',
    ...     confidence=1.0,
    ...     has_conflict=False,
    ...     conflict_chars=[],
    ...     total_quoted_fields=20,
    ...     method='detected',
    ... )
    >>> result.detected
    '"'
    >>> result.has_conflict
    False

    Conflicting file — mostly double quotes, a few single quotes:

    >>> result = TextDelimiterResult(
    ...     detected='"',
    ...     confidence=0.93,
    ...     has_conflict=True,
    ...     conflict_chars=["'"],
    ...     total_quoted_fields=43,
    ...     method='detected',
    ... )
    >>> result.conflict_chars
    ["'"]

    File with no quoted fields at all:

    >>> result = TextDelimiterResult(
    ...     detected=None,
    ...     confidence=0.0,
    ...     has_conflict=False,
    ...     conflict_chars=[],
    ...     total_quoted_fields=0,
    ...     method='detected',
    ... )
    >>> result.detected is None
    True
    """

    detected: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    has_conflict: bool = False
    conflict_chars: list[str] = Field(default_factory=list)
    total_quoted_fields: int = Field(ge=0)
    method: Literal['override', 'detected']

    @model_validator(mode='after')
    def _check_consistency(self) -> 'TextDelimiterResult':
        if self.detected is None and self.confidence != 0.0:
            raise ValueError('confidence must be 0.0 when detected is None')
        if self.has_conflict and not self.conflict_chars:
            raise ValueError('conflict_chars cannot be empty when has_conflict is True')
        if not self.has_conflict and self.conflict_chars:
            raise ValueError('has_conflict must be True when conflict_chars is non-empty')
        return self


class TextDelimiterDetector:
    """
    Infer the quote character used to delimit text fields in a CSV file.

    Combines three scoring dimensions — frequency, consistency, and
    position — into a single weighted score for each candidate.
    All three scores operate on raw lines without tokenisation, making
    them fully independent.

    Parameters
    ----------
    candidates : list of str, optional
        Quote character strings to evaluate.
        Defaults to :data:`_QUOTECHAR_CANDIDATES`.
    weights : dict of str to float, optional
        Weights applied to each scoring dimension. Keys must be
        ``'frequency'``, ``'consistency'``, and ``'position'``.
        Values must sum to ``1.0``.
        Defaults to :data:`_DEFAULT_WEIGHTS`.
    max_lines : int, optional
        Maximum number of lines read from the file as the detection
        sample. Defaults to ``50``.

    Examples
    --------
    >>> detector = TextDelimiterDetector()
    >>> result = detector.detect('data.csv', encoding_result='utf-8', sep=',')
    >>> result.detected
    '"'
    >>> result.method
    'detected'
    """

    def __init__(
        self,
        candidates: list[str] | None = None,
        weights: dict[str, float] | None = None,
        max_lines: int = 50,
    ) -> None:
        self.candidates = candidates if candidates is not None else _QUOTECHAR_CANDIDATES
        weights = weights if weights is not None else _DEFAULT_WEIGHTS
        self._validate_weights(weights)
        self.weights = weights
        self.max_lines = max_lines

    def _validate_weights(self, weights: dict[str, float]) -> None:
        """
        Validate the scoring dimension weights.

        Parameters
        ----------
        weights : dict of str to float
            Weights to validate. Keys must match exactly
            ``'frequency'``, ``'consistency'``, and ``'position'``.
            Values must sum to ``1.0``.

        Raises
        ------
        ValueError
            If *weights* contains unexpected or missing keys.
        ValueError
            If the values do not sum to ``1.0`` within a tolerance
            of ``1e-9``.
        """
        expected = set(_DEFAULT_WEIGHTS.keys())
        received = set(weights.keys())

        if received != expected:
            raise ValueError(
                f'Invalid weight keys: {received - expected}. '
                f'Expected: {expected}'
            )

        total = sum(weights.values())
        if not abs(total - 1.0) < 1e-9:
            raise ValueError(
                f'Weights must sum to 1.0, got {total:.6f}.'
            )

    def detect(
        self,
        path: Path | str,
        encoding_result: str,
        sep: str
    ) -> TextDelimiterResult:
        """
        Detect the quote character used in *path*.

        Parameters
        ----------
        path : Path or str
            File to inspect.
        encoding_result : str
            Encoding previously detected by :class:`EncodingDetector`.
            Used to decode the file bytes into a text sample.
        sep : str
            Field separator already determined by :class:`DelimiterDetector`.
            Required to compute co-occurrence and positional scores.

        Returns
        -------
        TextDelimiterResult
            Detected quote character with confidence and conflict
            information. ``detected`` is ``None`` when no quoting
            signals are found.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)

        sample = read_sample(path=path, encoding=encoding_result, max_lines=self.max_lines)
        lines = [line for line in sample.splitlines() if line.strip()]

        if not lines:
            return TextDelimiterResult(
                detected=None,
                confidence=0.0,
                has_conflict=False,
                conflict_chars=[],
                total_quoted_fields=0,
                method='detected',
            )

        scores = [
            self._score_candidate(lines, sep, candidate)
            for candidate in self.candidates
        ]

        active = [score for score in scores if score.total > 0.0]

        if not active:
            return TextDelimiterResult(
                detected=None,
                confidence=0.0,
                has_conflict=False,
                conflict_chars=[],
                total_quoted_fields=0,
                method='detected',
            )

        best = max(active, key=lambda score: score.total)
        others = [score for score in active if score.char != best.char]

        total_signal = sum(score.total for score in active)
        confidence = round(best.total / total_signal, 4) if total_signal > 0.0 else 0.0

        has_conflict = len(others) > 0
        conflict_chars = [other.char for other in others]
        total_quoted_fields = sum(s.field_count for s in active)

        return TextDelimiterResult(
            detected=best.char,
            confidence=confidence,
            has_conflict=has_conflict,
            conflict_chars=conflict_chars,
            total_quoted_fields=total_quoted_fields,
            method='detected',
        )

    def _score_candidate(
        self,
        lines: list[str],
        sep: str,
        candidate: str,
    ) -> _TextDelimiterCandidateScore:
        """
        Compute the three-dimensional score for *candidate* against *lines*.

        Parameters
        ----------
        lines : list of str
            Non-empty lines extracted from the sample.
        sep : str
            Field separator used to compute co-occurrence and position
            scores.
        candidate : str
            Quote character to evaluate.

        Returns
        -------
        _TextDelimiterCandidateScore
            Scores for each dimension, the weighted total, and the raw
            field count.
        """
        frequency   = self._frequency_score(lines, sep, candidate)
        consistency = self._consistency_score(lines, candidate)
        position, field_count = self._position_score(lines, sep, candidate)

        total = (
            frequency   * self.weights['frequency']
            + consistency * self.weights['consistency']
            + position    * self.weights['position']
        )

        return _TextDelimiterCandidateScore(
            char=candidate,
            frequency=frequency,
            consistency=consistency,
            position=position,
            total=round(total, 4),
            field_count=field_count,
        )

    def _frequency_score(self, lines: list[str], sep: str, candidate: str) -> float:
        """
        Compute the co-occurrence score of *candidate* with the field separator.

        Counts occurrences of the patterns ``sep+candidate`` and
        ``candidate+sep`` across all lines, the structural fingerprint
        of a quoting character wrapping a field. The raw count is passed
        through ``tanh`` to produce a value in ``(0.0, 1.0)`` that
        saturates for dense files without clipping.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        sep : str
            Field separator already known for this file.
        candidate : str
            Quote character to evaluate.

        Returns
        -------
        float
            Co-occurrence score in the range ``(0.0, 1.0)``.
            Returns ``0.0`` if no co-occurrence is found.

        Examples
        --------
        A line like ``"Alice","Bob"`` with sep ``','`` produces two hits
        for ``'"'``: the pattern ``,"`` and the pattern ``",``.
        """
        open_pattern  = sep + candidate
        close_pattern = candidate + sep

        hits = sum(
            line.count(open_pattern) + line.count(close_pattern)
            for line in lines
        )

        mean_hits = hits / len(lines)
        return round(math.tanh(mean_hits), 4)

    def _consistency_score(self, lines: list[str], candidate: str) -> float:
        """
        Compute the dominance ratio of *candidate* among all quoted fields.

        Counts how many times each candidate quote character appears at
        a quoting position (start or end of a field boundary) and
        returns the fraction that belongs to *candidate*. A file that
        exclusively uses ``"`` scores ``1.0``; one that mixes ``"`` and
        ``'`` equally scores ``0.5``.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        candidate : str
            Quote character to evaluate.

        Returns
        -------
        float
            Dominance ratio in the range ``[0.0, 1.0]``.
            Returns ``0.0`` if no candidate produces any hit at all.

        Notes
        -----
        This score is computed globally across all candidates so that
        the denominator reflects the true competition between them.
        The method counts raw occurrences of each candidate at line
        start, line end, and at ``\\n``-equivalent boundaries inside
        the raw text, without tokenisation.
        """
        total_hits: dict[str, int] = {}

        for char in self.candidates:
            count = sum(
                line.count(char)
                for line in lines
            )
            if count > 0:
                total_hits[char] = count

        if not total_hits:
            return 0.0

        candidate_hits = total_hits.get(candidate, 0)
        grand_total = sum(total_hits.values())

        return round(candidate_hits / grand_total, 4)

    def _position_score(
        self,
        lines: list[str],
        sep: str,
        candidate: str,
    ) -> tuple[float, int]:
        """
        Compute the structural position score for *candidate*.

        A quote character that genuinely delimits fields will appear
        consistently in key positions: the very start of a line, the
        very end of a line, immediately after the field separator, or
        immediately before the field separator. This method counts how
        many lines contain *candidate* in at least one of those four
        positions and normalises by the total number of lines.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        sep : str
            Field separator used to identify inter-field boundaries.
        candidate : str
            Quote character to evaluate.

        Returns
        -------
        score : float
            Fraction of lines where *candidate* appears in a structural
            position, in the range ``[0.0, 1.0]``.
        field_count : int
            Raw number of lines that produced at least one positional
            hit. Returned alongside the score for use as a diagnostic
            counter in :class:`_TextDelimiterCandidateScore`.

        Notes
        -----
        The four positions checked per line are:

        * ``line[0] == candidate`` — opens the first field.
        * ``line[-1] == candidate`` — closes the last field.
        * ``sep + candidate`` present in the line — opens a mid-line field.
        * ``candidate + sep`` present in the line — closes a mid-line field.

        This deliberately overlaps with :meth:`_frequency_score`: the
        two scores are independent by design. ``_frequency_score``
        measures *density* (how many co-occurrences per line on average);
        ``_position_score`` measures *coverage* (how many lines carry
        at least one structural hit). Both are needed to distinguish a
        dominant quotechar from noise.
        """
        sep_open  = sep + candidate
        sep_close = candidate + sep

        hits = 0

        for line in lines:
            if not line:
                continue

            line_hit = (
                line[0] == candidate
                or line[-1] == candidate
                or sep_open in line
                or sep_close in line
            )

            if line_hit:
                hits += 1

        score = round(hits / len(lines), 4) if lines else 0.0
        return score, hits

    def _iter_fields(self, line: str, sep: str) -> Iterator[str]:
        """
        Tokenise *line* into fields respecting RFC 4180 quoting rules.

        Uses :meth:`str.find` to skip over quoted blocks rather than
        iterating character by character, keeping the inner loop at
        ``O(n)`` with a low constant.

        Parameters
        ----------
        line : str
            A single CSV line with the line ending already stripped.
        sep : str
            Field separator. Accepts multi-character separators.

        Yields
        ------
        str
            Each field value with enclosing quote characters removed.
            Doubled quote characters inside a quoted field are preserved
            as-is and left for the caller to unescape if needed.

        Notes
        -----
        Mixed quote characters within the same field (e.g. a field
        opened with ``"`` and containing a bare ``'``) are treated as
        literal values — detection of such anomalies is delegated to
        higher-level diagnostics.

        Newlines embedded inside quoted fields are not handled here
        because *line* is expected to be a single pre-split line.
        Multi-line field reconstruction belongs to a higher-level parser.

        This method is not used by the three scoring dimensions, which
        operate on raw lines. It is kept as an alternative tokeniser
        available to callers that need field-level access.

        Examples
        --------
        >>> list(detector._iter_fields('"São Paulo, SP",João,42', ','))
        ['"São Paulo, SP"', 'João', '42']

        >>> list(detector._iter_fields('a,,c', ','))
        ['a', '', 'c']
        """
        sep_len = len(sep)
        line_len = len(line)
        cursor = 0

        while cursor <= line_len:
            if cursor == line_len:
                yield ''
                break

            if line[cursor] in self.candidates:
                quotechar_open = line[cursor]
                closing_index = cursor + 1

                while True:
                    closing_index = line.find(quotechar_open, closing_index)

                    if closing_index == -1:
                        yield line[cursor:]
                        return

                    next_index = closing_index + 1
                    is_escaped_quote = (
                        next_index < line_len
                        and line[next_index] == quotechar_open
                    )

                    if is_escaped_quote:
                        closing_index = next_index + 1
                        continue

                    yield line[cursor: closing_index + 1]
                    cursor = closing_index + 1

                    if line[cursor: cursor + sep_len] == sep:
                        cursor += sep_len

                    break

            else:
                sep_index = line.find(sep, cursor)

                if sep_index == -1:
                    yield line[cursor:]
                    return

                yield line[cursor:sep_index]
                cursor = sep_index + sep_len