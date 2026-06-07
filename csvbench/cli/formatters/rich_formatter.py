from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from csvbench.cli.formatters.base import BaseFormatter
from csvbench.core.models import DiagnosticReport, Issue, Severity

_stdout_console = Console(highlight=False)
_stderr_console = Console(stderr=True, highlight=False)


class RichFormatter(BaseFormatter):
    """Render diagnostic reports as styled Rich terminal output.

    Uses a summary panel for file metadata and a separate table for
    issues.

    Parameters
    ----------
    output : Path or None
        Ignored for Rich output; always writes to the terminal.
        Present for API symmetry with :class:`JsonFormatter`.
    quiet : bool
        Print a single ``PASS`` / ``FAIL`` summary line only.
    verbose : bool
        Add a ``Suggestion`` column to the issues table.

    Examples
    --------
    >>> fmt = RichFormatter()
    >>> fmt.render(report)
    """

    def __init__(
        self,
        output: Path | None = None,
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        super().__init__(output=output, quiet=quiet, verbose=verbose)

    def render(self, report: DiagnosticReport) -> None:
        """Render a diagnostic report to the terminal.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.
        """
        if self.quiet:
            self._render_quiet(report)
            return

        self._render_panel(report)

        if report.issues:
            _stdout_console.print()
            self._render_issues_table(report.issues)

        if not report.issues:
            _stdout_console.print()
            _stdout_console.print('  [bold green]✔[/bold green]  No issues found.')

    def render_error(
        self,
        title: str,
        message: str,
        suggestion: str,
    ) -> None:
        """Render an error panel to stderr.

        Parameters
        ----------
        title : str
            Panel title shown in the border.
        message : str
            Description of what went wrong.
        suggestion : str
            Actionable hint shown below the message.
        """
        content = Text()
        content.append(f'{message}\n', style='white')
        content.append(f'\n💡 {suggestion}', style='dim')

        _stderr_console.print(
            Panel(
                content,
                title=f'[bold red]❌ {title}[/bold red]',
                border_style='red',
                padding=(1, 2),
            )
        )

    def _render_quiet(self, report: DiagnosticReport) -> None:
        """Print a single PASS / FAIL summary line.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.
        """
        path = report.display_path

        if report.has_errors or report.has_warnings:
            parts: list[str] = []
            if report.error_count:
                parts.append(
                    f'{report.error_count} '
                    f'{"error" if report.error_count == 1 else "errors"}'
                )
            if report.warning_count:
                parts.append(
                    f'{report.warning_count} '
                    f'{"warning" if report.warning_count == 1 else "warnings"}'
                )
            detail = ', '.join(parts)
            _stdout_console.print(f'[bold red]FAIL[/bold red] {path} ({detail})')
        else:
            _stdout_console.print(f'[bold green]PASS[/bold green] {path}')

    def _render_panel(self, report: DiagnosticReport) -> None:
        """Render the summary metadata panel.

        Parameters
        ----------
        report : DiagnosticReport
            Completed inspection report.
        """
        rows: list[tuple[str, str]] = [
            ('📁 File', report.display_path),
            ('🔤 Encoding', (
                f'{report.encoding}  '
                f'[dim]({report.encoding_confidence * 100:.0f}% confidence - {report.encoding_method})[/dim]'
            )),
            ('🔀 Separator', (
                f'{repr(report.delimiter)}  '
                f'[dim]({report.delimiter_confidence * 100:.0f}% confidence - {report.delimiter_method})[/dim]'
            )),
            ('💬 Quotechar', (
                f'{repr(report.quotechar)}  '
                f'[dim]({report.quotechar_confidence * 100:.0f}% confidence - {report.quotechar_method})[/dim]'
            )),
            ('📊 Columns', str(report.column_count)),
            ('📈 Lines', str(report.row_count)),
            ('❌ Errors', _coloured_count(report.error_count, 'red')),
            ('⚠️  Warnings', _coloured_count(report.warning_count, 'yellow')),
            ('⏱️  Elapsed', f'{report.elapsed_seconds:.4f}s'),
        ]

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style='dim', justify='right')
        grid.add_column()

        for label, value in rows:
            grid.add_row(label, value)

        _stdout_console.print(
            Panel(
                grid,
                title='[bold]csvbench inspect[/bold]',
                border_style='blue',
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )

    def _render_issues_table(self, issues: list[Issue]) -> None:
        """Render the issues as a Rich table.

        Includes a ``Suggestion`` column when *verbose* is enabled.

        Parameters
        ----------
        issues : list[Issue]
            Non-empty list of diagnostic findings.
        """
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            highlight=False,
            pad_edge=True,
        )

        table.add_column('#', style='dim', justify='right', width=4)
        table.add_column('Severity', justify='left', width=10)
        table.add_column('Code', justify='left', width=22)
        table.add_column('Line', justify='right', width=7)
        table.add_column('Detail', justify='left')

        if self.verbose:
            table.add_column('Suggestion', justify='left', style='dim')

        for idx, issue in enumerate(issues, start=1):
            severity_text = _severity_label(issue.severity)
            line_text = str(issue.line) if issue.line is not None else '—'

            row: list[str | Text] = [
                str(idx),
                severity_text,
                issue.code,
                line_text,
                issue.detail,
            ]

            if self.verbose:
                row.append(issue.suggestion or '—')

            table.add_row(*row)

        _stdout_console.print(table)

def _severity_label(severity: Severity) -> Text:
    """Return a coloured Rich Text label for a severity level.

    Parameters
    ----------
    severity : Severity
        The severity enum value.

    Returns
    -------
    Text
        Styled Rich Text object.
    """
    _styles: dict[Severity, tuple[str, str]] = {
        Severity.ERROR:   ('ERROR',   'bold red'),
        Severity.WARNING: ('WARNING', 'bold yellow'),
        Severity.INFO:    ('INFO',    'bold blue'),
    }
    label, style = _styles[severity]
    return Text(label, style=style)

def _coloured_count(count: int, colour: str) -> str:
    """Return a coloured markup string for a numeric count.

    Shows plain white when the count is zero to avoid alarming the user
    unnecessarily.

    Parameters
    ----------
    count : int
        The numeric value to display.
    colour : str
        Rich colour name applied when ``count > 0``.

    Returns
    -------
    str
        Rich markup string.
    """
    if count == 0:
        return '[dim]0[/dim]'
    return f'[bold {colour}]{count}[/bold {colour}]'