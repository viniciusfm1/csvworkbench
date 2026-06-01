from __future__ import annotations

import json
import sys
from pathlib import Path

from csvbench.cli.formatters.base import BaseFormatter
from csvbench.core.models import DiagnosticReport


class JsonFormatter(BaseFormatter):
    """Render diagnostic reports as JSON.

    Writes to stdout by default.  When *output* is provided, writes to
    that file instead — useful for saving reports programmatically.

    Error output always goes to stderr so that it does not corrupt a
    JSON pipe even when the main output is being redirected.

    Parameters
    ----------
    output : Path or None
        Optional path to write the JSON report.  ``None`` means stdout.
    quiet : bool
        Emit a reduced summary object instead of the full report.
    verbose : bool
        No effect for JSON output — all fields are always present in
        the full report.  Accepted for API symmetry.

    Examples
    --------
    >>> fmt = JsonFormatter(output=Path('report.json'))
    >>> fmt.render(report)
    """

    def __init__(
        self,
        output: Path | None = None,
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        super().__init__(output=output, quiet=quiet, verbose=verbose)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def render(self, report: DiagnosticReport) -> None:
        """Serialise and emit the diagnostic report as JSON.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.
        """
        payload = self._build_quiet_payload(report) if self.quiet else self._build_full_payload(report)
        self._emit(payload)

    def render_error(
        self,
        title: str,
        message: str,
        suggestion: str,
    ) -> None:
        """Write an error object to stderr as JSON.

        Writes to stderr so that the error never pollutes a stdout pipe
        that expects a valid report object.

        Parameters
        ----------
        title : str
            Short label for the error, e.g. ``'File not found'``.
        message : str
            Full description of what went wrong.
        suggestion : str
            Actionable hint for resolving the problem.
        """
        payload = {
            'error': {
                'title': title,
                'message': message,
                'suggestion': suggestion,
            }
        }
        sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stderr.write('\n')

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    def _build_full_payload(self, report: DiagnosticReport) -> dict:
        """Build the full JSON payload from a diagnostic report.

        Uses Pydantic's ``model_dump`` with ``mode='json'`` so that
        all field types (``Path``, ``Enum``) are serialised to their
        JSON-native equivalents without manual conversion.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.

        Returns
        -------
        dict
            JSON-serialisable dictionary representing the full report.
        """
        return report.model_dump(mode='json')

    def _build_quiet_payload(self, report: DiagnosticReport) -> dict:
        """Build a reduced summary payload for --quiet mode.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.

        Returns
        -------
        dict
            Reduced JSON object with status, counts, and path only.
        """
        return {
            'file_path': str(report.display_path),
            'status': 'fail' if (report.has_errors or report.has_warnings) else 'pass',
            'error_count': report.error_count,
            'warning_count': report.warning_count,
        }

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def _emit(self, payload: dict) -> None:
        """Write *payload* as indented JSON to stdout or *self.output*.

        Parameters
        ----------
        payload : dict
            JSON-serialisable dictionary to emit.
        """
        serialised = json.dumps(payload, ensure_ascii=False, indent=2)

        if self.output is not None:
            self.output.write_text(serialised, encoding='utf-8')
        else:
            sys.stdout.write(serialised)
            sys.stdout.write('\n')