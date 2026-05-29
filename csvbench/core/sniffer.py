from __future__ import annotations

import re
import math
from dataclasses import dataclass
from csvbench.core.detectors.delimiter import DelimiterResult


_SINGLE_CHAR_CANDIDATES: list[str] = [',', ';', '|', '\t', '\x07']
_MULTICHAR_CANDIDATES: list[str] = ['||', '::', '\t\t', ]

_DEFAULT_CANDIDATES: list[str] = _SINGLE_CHAR_CANDIDATES + _MULTICHAR_CANDIDATES

_DEFAULT_WEIGHTS: dict[str, float] = {
    'frequency':   0.2,
    'consistency': 0.4,
    'position':    0.2,
    'quoting':     0.2,
}


@dataclass
class _CandidateScore:
    """
    Intermediate scoring result for a single delimiter candidate.

    Parameters
    ----------
    candidate : str
        The delimiter string being evaluated.
    frequency : float
        Normalised frequency score in the range ``[0.0, 1.0]``.
    consistency : float
        Column-count consistency score in the range ``[0.0, 1.0]``.
    position : float
        Positional regularity score in the range ``[0.0, 1.0]``.
    quoting : float
        Quoting penalty score in the range ``[0.0, 1.0]``.
        Higher means the candidate appears less inside quoted fields.
    total : float
        Weighted sum of the four scores.
    """

    candidate: str
    frequency: float
    consistency: float
    position: float
    quoting: float
    total: float


class DelimiterSniffer:
    """
    Infer the field delimiter of a CSV-like text sample.

    Combines four scoring dimensions — frequency, consistency, position,
    and quoting — into a single weighted score for each candidate.
    The candidate with the highest total score is returned.

    Parameters
    ----------
    candidates : list of str, optional
        Delimiter strings to evaluate. Accepts both single-character
        and multi-character candidates. Defaults to
        :data:`_DEFAULT_CANDIDATES`.
    weights : dict of str to float, optional
        Weights applied to each scoring dimension. Keys must be
        ``'frequency'``, ``'consistency'``, ``'position'``, and
        ``'quoting'``. Values must sum to ``1.0``.
        Defaults to :data:`_DEFAULT_WEIGHTS`.

    Examples
    --------
    >>> sniffer = DelimiterSniffer()
    >>> result = sniffer.sniff('id,name,city\\n1,Alice,SP\\n2,Bob,RJ\\n')
    >>> result.sep
    ','
    >>> result.method
    'sniffed'
    """

    def __init__(
        self,
        candidates: list[str] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.candidates = candidates if candidates is not None else _DEFAULT_CANDIDATES
        weights = weights if weights is not None else _DEFAULT_WEIGHTS
        self._validate_weights(weights)
        self.weights = weights

    def _validate_weights(self, weights: dict[str, float]) -> None:
        """
        Validate the scoring dimension weights.

        Parameters
        ----------
        weights : dict of str to float
            Weights to validate. Keys must match exactly
            ``'frequency'``, ``'consistency'``, ``'position'``
            and ``'quoting'``. Values must sum to ``1.0``.

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
    
    def sniff(self, sample: str) -> DelimiterResult:
        """
        Analyse *sample* and return the most likely delimiter.

        Parameters
        ----------
        sample : str
            Plain text sample of the CSV file, typically the first
            ``N`` lines produced by :meth:`DelimiterDetector._read_sample`.

        Returns
        -------
        DelimiterResult
            Best candidate with ``method='sniffed'`` and a confidence
            derived from its total score.

        Raises
        ------
        ValueError
            If *sample* is empty or contains no non-empty lines.

        Examples
        --------
        >>> result = DelimiterSniffer().sniff('a;b;c\\n1;2;3\\n')
        >>> result.sep
        ';'
        """
        
        lines = [line for line in sample.splitlines() if line.strip()]

        if not lines:
            raise ValueError('Sample is empty or contains no non-empty lines.')

        scores = [
            self._score_candidate(lines, candidate)
            for candidate in self.candidates
        ]

        best = max(scores, key=lambda s: (s.total, -len(s.candidate)))

        return DelimiterResult(
            sep=best.candidate,
            confidence=round(best.total, 4),
            method='sniffed',
        )

    def _score_candidate(self, lines: list[str], candidate: str) -> _CandidateScore:
        """
        Compute the four-dimensional score for *candidate* against *lines*.

        Parameters
        ----------
        lines : list of str
            Non-empty lines extracted from the sample.
        candidate : str
            Delimiter string to evaluate.

        Returns
        -------
        _CandidateScore
            Scores for each dimension and the weighted total.
        """
        
        frequency   = self._frequency_score(lines, candidate)
        consistency = self._consistency_score(lines, candidate)
        position    = self._position_score(lines, candidate)
        quoting     = self._quoting_score(lines, candidate)

        total = (
            frequency   * self.weights['frequency']
            + consistency * self.weights['consistency']
            + position    * self.weights['position']
            + quoting     * self.weights['quoting']
        )

        return _CandidateScore(
            candidate=candidate,
            frequency=frequency,
            consistency=consistency,
            position=position,
            quoting=quoting,
            total=total,
        )

    def _frequency_score(self, lines: list[str], candidate: str) -> float:
        """
        Compute the normalised frequency score for *candidate*.

        Counts the total number of occurrences of *candidate* across
        all *lines* and normalises by the number of lines. Higher
        frequency relative to other candidates indicates a more likely
        delimiter.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        candidate : str
            Delimiter string to count.

        Returns
        -------
        float
            Normalised frequency score in the range ``[0.0, 1.0]``.
        """
        
        pattern = re.compile(re.escape(candidate))
        counts = [len(pattern.findall(line)) for line in lines]
        mean = sum(counts) / len(lines)
        return round(math.tanh(mean), 4)

    def _consistency_score(self, lines: list[str], candidate: str) -> float:
        """
        Compute the column-count consistency score for *candidate*.

        A true delimiter splits every line into the same number of
        columns. Measures this by computing the variance of per-line
        split counts — lower variance yields a higher score.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        candidate : str
            Delimiter string to evaluate.

        Returns
        -------
        float
            Consistency score in the range ``[0.0, 1.0]``.
            Returns ``0.0`` if *candidate* never appears in *lines*.
        """
        pattern = re.compile(re.escape(candidate))
        counts = [len(pattern.findall(line)) for line in lines]

        if max(counts) == 0:
            return 0.0

        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)

        return round(1.0 / (1.0 + variance), 4)

    def _position_score(self, lines: list[str], candidate: str) -> float:
        """
        Compute the positional regularity score for *candidate*.

        True delimiters tend to appear at predictable positions across
        lines because fields have similar lengths. Measures the standard
        deviation of occurrence positions within each line — lower
        deviation yields a higher score.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        candidate : str
            Delimiter string to evaluate.

        Returns
        -------
        float
            Positional regularity score in the range ``[0.0, 1.0]``.
            Returns ``0.0`` if *candidate* never appears in *lines*.
        """
        pattern = re.compile(re.escape(candidate))

        normalised_positions_per_line = [
            [
                match.start() / len(line)
                for match in pattern.finditer(line)
            ]
            for line in lines
            if pattern.search(line)
        ]

        if not normalised_positions_per_line:
            return 0.0

        max_occurrences = max(
            len(positions) for positions in normalised_positions_per_line
        )

        aligned_lines = [
            positions
            for positions in normalised_positions_per_line
            if len(positions) == max_occurrences
        ]

        deviations_per_column = [
            math.sqrt(
                sum(
                    (current - previous) ** 2
                    for current, previous in zip(column[1:], column[:-1])
                )
                / len(column)
            )
            for column in zip(*aligned_lines)
            if len(column) > 1
        ]

        if not deviations_per_column:
            return 1.0

        mean_deviation = sum(deviations_per_column) / len(deviations_per_column)
        return round(1.0 / (1.0 + mean_deviation), 4)

    def _quoting_score(self, lines: list[str], candidate: str) -> float:
        """
        Compute the quoting penalty score for *candidate*.

        A true delimiter should not appear unprotected inside quoted
        fields. Uses a regular expression to strip quoted regions from
        each line before counting occurrences. A higher ratio of
        outside-quote occurrences to total occurrences yields a higher
        score.

        Parameters
        ----------
        lines : list of str
            Non-empty lines from the sample.
        candidate : str
            Delimiter string to evaluate.

        Returns
        -------
        float
            Quoting score in the range ``[0.0, 1.0]``.
            Returns ``1.0`` if *candidate* never appears inside quotes.
            Returns ``0.0`` if *candidate* only appears inside quotes.
        """
        pattern = re.compile(re.escape(candidate))
        quoted_region = re.compile(r'"[^"]*"')

        total_occurrences = sum(
            len(pattern.findall(line))
            for line in lines
        )

        if total_occurrences == 0:
            return 1.0

        occurrences_outside_quotes = sum(
            len(pattern.findall(quoted_region.sub('', line)))
            for line in lines
        )

        return round(occurrences_outside_quotes / total_occurrences, 4)