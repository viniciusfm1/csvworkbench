from __future__ import annotations

import os
from importlib.metadata import version, PackageNotFoundError
from typing import Annotated

import typer

from csvbench.cli.commands.inspect import inspect_command

app = typer.Typer(
    name='csvbench',
    help=(
        '[bold]csvbench[/bold] — diagnose and repair malformed CSV files.\n\n'
        'Run any command with [green]--help[/green] for detailed usage.'
    ),
    epilog='Docs & source: [blue]https://github.com/viniciusfm1/csvworkbench[/blue]',
    rich_markup_mode='rich',
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
    context_settings={'help_option_names': ['--help', '-h']},
)

app.command('inspect')(inspect_command)

# app.add_typer(repair_command.app,  name='repair',  help='Repair a malformed CSV file.')
# app.add_typer(profile_command.app, name='profile', help='Profile a CSV file for statistics.')
# app.add_typer(diff_command.app,    name='diff',    help='Diff two CSV files.')

def _get_version() -> str:
    """Return the installed package version, or a fallback string.

    Uses ``importlib.metadata`` so the version is always read from
    ``pyproject.toml`` at runtime and never duplicated in source code.

    Returns
    -------
    str
        Version string, e.g. ``'0.1.0'``, or ``'unknown'`` when the
        package is not installed (e.g. running from a bare checkout).
    """
    try:
        return version('csvbench')
    except PackageNotFoundError:
        return 'unknown'


def _version_callback(value: bool) -> None:  # noqa: FBT001
    """Print version and exit when --version is passed.

    Parameters
    ----------
    value : bool
        ``True`` when the flag is present on the command line.
    """
    if value:
        typer.echo(f'csvbench {_get_version()}')
        raise typer.Exit()


def _apply_no_color() -> None:
    """Disable Rich colour output by setting the NO_COLOR env variable.

    Respects the NO_COLOR convention (https://no-color.org): if the
    variable is already set in the environment this is a no-op.
    Setting it here — before any Rich output is produced — ensures
    that *all* downstream formatters pick up the preference without
    needing explicit wiring.
    """
    os.environ.setdefault('NO_COLOR', '1')


@app.callback()
def main(
    version: Annotated[  # noqa: A002
        bool,
        typer.Option(
            '--version',
            callback=_version_callback,
            is_eager=True,
            help='Show the installed version and exit.',
            show_default=False,
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            '--no-color',
            is_eager=True,
            help=(
                'Disable colour output. '
                'Also honoured via the NO_COLOR environment variable.'
            ),
            show_default=False,
        ),
    ] = False,
) -> None:
    """Global options applied before any subcommand runs."""
    if no_color or os.environ.get('NO_COLOR'):
        _apply_no_color()

if __name__ == '__main__':
    app()