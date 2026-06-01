from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from csvbench.core.models import DiagnosticReport


class BaseFormatter(ABC):
    """Abstract base class for all csvbench output formatters.

    Defines the two-method contract every formatter must implement:
    :meth:`render` for the happy path and :meth:`render_error` for
    I/O and validation failures.

    Subclasses receive display preferences at construction time so that
    individual ``render`` calls stay argument-free and the formatter can
    be passed around as a plain object without callers knowing its
    configuration.

    Parameters
    ----------
    output : Path or None
        Optional file path to write output to.  ``None`` means stdout.
        Subclasses decide whether to honour this (e.g. only meaningful
        for machine-readable formats like JSON).
    quiet : bool
        When ``True``, render a single summary line instead of the full
        report.
    verbose : bool
        When ``True``, render extended detail beyond the default output.

    Notes
    -----
    ``quiet`` and ``verbose`` are mutually exclusive.  Enforcement is
    handled upstream by :class:`~csvbench.cli.options.BaseOptions`;
    formatters assume the combination is already valid.
    """

    def __init__(
        self,
        output: Path | None = None,
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        self.output = output
        self.quiet = quiet
        self.verbose = verbose

    @abstractmethod
    def render(self, report: DiagnosticReport) -> None:
        """Render a completed diagnostic report.

        Parameters
        ----------
        report : DiagnosticReport
            The immutable report produced by
            :meth:`~csvbench.core.workbench.CsvWorkbench.run_inspect`.
        """

    @abstractmethod
    def render_error(
        self,
        title: str,
        message: str,
        suggestion: str,
    ) -> None:
        """Render an error that prevented the inspection from running.

        Must write to stderr so that the error does not pollute stdout
        output that may be piped to another process.

        Parameters
        ----------
        title : str
            Short label for the error panel or JSON key, e.g.
            ``'File not found'``.
        message : str
            Full description of what went wrong.
        suggestion : str
            Actionable hint for resolving the problem.
        """