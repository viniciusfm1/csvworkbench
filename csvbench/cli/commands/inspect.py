from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import IO

import typer

from csvbench.cli.options import ExitCode, InspectOptions
from csvbench.core.models import DiagnosticReport
from csvbench.core.workbench import CsvWorkbench

from csvbench.cli.formatters import get_formatter

def inspect_command(
    file: str = typer.Argument(
        ...,
        metavar='FILE',
        help="CSV file to inspect. Pass '-' to read from stdin.",
        show_default=False,
    ),
    format: str = typer.Option(
        'rich',
        '--format', '-f',
        help="Output format: 'rich' (default) or 'json'.",
        show_default=True,
    ),
    output: Path | None = typer.Option(
        None,
        '--output', '-o',
        help='Write output to FILE instead of stdout. Applies to --format json only.',
        show_default=False,
    ),
    quiet: bool = typer.Option(
        False,
        '--quiet', '-q',
        help='Print a single summary line only. Mutually exclusive with --verbose.',
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        '--verbose', '-v',
        help='Print extended detail. Mutually exclusive with --quiet.',
        is_flag=True,
    ),
) -> None:
    """Inspect a CSV file and report structural issues.

    Detects encoding problems, delimiter mismatches, column count
    inconsistencies, duplicate or empty headers, and more.

    \b
    Examples
    --------
    csvbench inspect data.csv
    csvbench inspect data.csv --format json --output report.json
    csvbench inspect data.csv --verbose
    cat data.csv | csvbench inspect -
    """
    from pydantic import ValidationError

    formatter = get_formatter(format, output=output, quiet=quiet, verbose=verbose)

    try:
        options = InspectOptions(
            file=file,
            format=format,  # type: ignore[arg-type]
            output=output,
            quiet=quiet,
            verbose=verbose,
        )
    except ValidationError as exc:
        formatter.render_error(
            title='Invalid options',
            message=_first_validation_message(exc),
            suggestion='Run `csvbench inspect --help` for usage.',
        )
        raise SystemExit(ExitCode.IO_ERROR)

    report, exit_code = _run_inspect(options, formatter)

    formatter.render(report)
    raise SystemExit(exit_code)

def _run_inspect(
    options: InspectOptions,
    formatter: object,
) -> tuple[DiagnosticReport, ExitCode]:
    """Execute the inspection and return the report and exit code.

    Separating this from the Typer callback allows unit tests to call
    ``_run_inspect(options, mock_formatter)`` without spinning up a CLI
    process.

    Parameters
    ----------
    options : InspectOptions
        Validated command options.
    formatter : BaseFormatter
        Formatter instance used to render errors during I/O failures.
        The type is ``object`` here to avoid a circular import at module
        level; callers always pass a concrete formatter subclass.

    Returns
    -------
    tuple of (DiagnosticReport, ExitCode)
        The diagnostic report and the appropriate exit code.

    Raises
    ------
    SystemExit
        On any I/O error that prevents the inspection from running.
    """
    is_stdin = options.file == '-'

    if is_stdin:
        report = _inspect_stdin(options, formatter)
    else:
        report = _inspect_file(options, formatter)

    return report, _resolve_exit_code(report)


def _inspect_file(
    options: InspectOptions,
    formatter: object,
) -> DiagnosticReport:
    """Run inspection on a file path.

    Parameters
    ----------
    options : InspectOptions
        Validated command options. ``options.file`` must be a ``Path``.
    formatter : BaseFormatter
        Used to render I/O errors as styled panels.

    Returns
    -------
    DiagnosticReport
        Completed diagnostic report.

    Raises
    ------
    SystemExit
        With ``ExitCode.IO_ERROR`` on any filesystem or decoding failure.
    """
    path = Path(options.file)  # type: ignore[arg-type]

    if not path.exists():
        formatter.render_error(
            title='File not found',
            message=f'{path} does not exist.',
            suggestion='Check the path and try again.',
        )
        raise SystemExit(ExitCode.IO_ERROR)

    if not path.is_file():
        formatter.render_error(
            title='Not a file',
            message=f'{path} is a directory or special file.',
            suggestion='Pass a regular CSV file path.',
        )
        raise SystemExit(ExitCode.IO_ERROR)

    return _run_workbench(path, formatter)


def _inspect_stdin(
    options: InspectOptions,  # noqa: ARG001  — kept for API symmetry
    formatter: object,
) -> DiagnosticReport:
    """Run inspection on content piped through stdin.

    Reads stdin into a temporary file so that :class:`CsvWorkbench` can
    use its standard ``Path``-based API without modification.  The temp
    file is deleted immediately after the workbench finishes.

    Parameters
    ----------
    options : InspectOptions
        Validated command options (unused here, kept for API symmetry).
    formatter : BaseFormatter
        Used to render errors as styled panels.

    Returns
    -------
    DiagnosticReport
        Completed diagnostic report with ``file_path`` set to
        ``Path('<stdin>')`` for display purposes.

    Raises
    ------
    SystemExit
        With ``ExitCode.IO_ERROR`` when stdin is empty or unreadable.
    """
    try:
        content: bytes = sys.stdin.buffer.read()
    except OSError as exc:
        formatter.render_error(
            title='Stdin read error',
            message=str(exc),
            suggestion='Ensure the pipe is producing data and try again.',
        )
        raise SystemExit(ExitCode.IO_ERROR)

    if not content.strip():
        formatter.render_error(
            title='Empty input',
            message='No data received from stdin.',
            suggestion='Pipe a CSV file into csvbench, e.g.: cat data.csv | csvbench inspect -',
        )
        raise SystemExit(ExitCode.IO_ERROR)

    with tempfile.NamedTemporaryFile(suffix='.csv', delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        report = _run_workbench(Path(tmp.name), formatter)

    return report.model_copy(update={'file_path': Path('<stdin>')})


def _run_workbench(
    path: Path,
    formatter: object,
) -> DiagnosticReport:
    """Instantiate :class:`CsvWorkbench`, run read + inspect, return report.

    Parameters
    ----------
    path : Path
        Path to the CSV file (real file or temp file from stdin).
    formatter : BaseFormatter
        Used to render runtime errors as styled panels.

    Returns
    -------
    DiagnosticReport
        Completed diagnostic report.

    Raises
    ------
    SystemExit
        With ``ExitCode.IO_ERROR`` on ``PermissionError``,
        ``UnicodeDecodeError``, or ``ValueError`` (empty file).
    """
    _IO_ERRORS: tuple[type[Exception], ...] = (
        PermissionError,
        UnicodeDecodeError,
        ValueError,
        OSError,
    )

    try:
        return CsvWorkbench(path).read().run_inspect()
    except FileNotFoundError:
        formatter.render_error(
            title='File not found',
            message=f'{path} was removed before it could be read.',
            suggestion='Check that the file is not being modified concurrently.',
        )
        raise SystemExit(ExitCode.IO_ERROR)
    except _IO_ERRORS as exc:
        formatter.render_error(
            title='Could not read file',
            message=str(exc),
            suggestion=(
                'The file may be corrupted, have wrong permissions, '
                'or use an unsupported encoding.'
            ),
        )
        raise SystemExit(ExitCode.IO_ERROR)

def _resolve_exit_code(report: DiagnosticReport) -> ExitCode:
    """Map a completed report to the appropriate exit code.

    Parameters
    ----------
    report : DiagnosticReport
        The finished diagnostic report.

    Returns
    -------
    ExitCode
        ``ERROR`` when any error-level issue exists, ``WARNING`` when
        only warnings exist, ``OK`` when the file is clean.

    Examples
    --------
    >>> _resolve_exit_code(report_with_errors)
    <ExitCode.ERROR: 2>
    >>> _resolve_exit_code(clean_report)
    <ExitCode.OK: 0>
    """
    if report.has_errors:
        return ExitCode.ERROR
    if report.has_warnings:
        return ExitCode.WARNING
    return ExitCode.OK


def _first_validation_message(exc: 'ValidationError') -> str:  # type: ignore[name-defined]
    """Extract the first human-readable message from a Pydantic ValidationError.

    Parameters
    ----------
    exc : ValidationError
        The exception raised by Pydantic during model construction.

    Returns
    -------
    str
        The ``msg`` field of the first error entry.
    """
    errors = exc.errors()
    if errors:
        return errors[0].get('msg', str(exc))
    return str(exc)