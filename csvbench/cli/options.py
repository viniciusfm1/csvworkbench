from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExitCode(IntEnum):
    """Semantic exit codes for all csvbench CLI commands.

    Using ``IntEnum`` allows direct use in ``raise SystemExit(ExitCode.ERROR)``
    and comparisons with plain integers without explicit casting.

    Attributes
    ----------
    OK : int
        Inspection completed with no issues found.
    WARNING : int
        Inspection completed; at least one WARNING-level issue found.
    ERROR : int
        Inspection completed; at least one ERROR-level issue found.
    IO_ERROR : int
        Command could not run due to a filesystem or I/O problem
        (file not found, permission denied, unreadable content, etc.).

    Examples
    --------
    >>> raise SystemExit(ExitCode.OK)
    >>> ExitCode.ERROR > ExitCode.WARNING
    True
    >>> ExitCode.OK == 0
    True
    """

    OK = 0
    WARNING = 1
    ERROR = 2
    IO_ERROR = 3


class BaseOptions(BaseModel):
    """Shared options inherited by every csvbench command.

    Parameters
    ----------
    format : {'rich', 'json'}
        Output format.  ``'rich'`` renders a styled terminal panel;
        ``'json'`` emits a machine-readable JSON object to stdout
        (or to *output* when provided).  Defaults to ``'rich'``.
    output : Path or None
        Optional path to write the output to.  When ``None`` (default)
        output goes to stdout.  Only meaningful when *format* is
        ``'json'``; Rich output is always written to the terminal.
    quiet : bool
        Suppress all output except a single summary line
        (``PASS file.csv`` / ``FAIL file.csv (2 errors, 1 warning)``).
        Mutually exclusive with *verbose*.
    verbose : bool
        Emit additional detail beyond the default output, such as
        samples of offending lines.  Mutually exclusive with *quiet*.

    Raises
    ------
    ValueError
        If both *quiet* and *verbose* are ``True``.

    Examples
    --------
    >>> BaseOptions(format='json', output=Path('report.json'))
    BaseOptions(format='json', output=PosixPath('report.json'), quiet=False, verbose=False)
    >>> BaseOptions(quiet=True, verbose=True)
    ValueError: ...
    """

    format: Literal['rich', 'json'] = Field(
        default='rich',
        description="Output format: 'rich' for terminal display, 'json' for programmatic use.",
    )
    output: Path | None = Field(
        default=None,
        description='Write output to this path instead of stdout. Applies to json format only.',
    )
    quiet: bool = Field(
        default=False,
        description='Print a single summary line only. Mutually exclusive with verbose.',
    )
    verbose: bool = Field(
        default=False,
        description='Print extended detail. Mutually exclusive with quiet.',
    )

    model_config = {'frozen': True}

    @model_validator(mode='after')
    def _forbid_quiet_and_verbose(self) -> 'BaseOptions':
        """Raise if both quiet and verbose are enabled simultaneously.

        Parameters
        ----------
        self : BaseOptions
            The fully constructed model instance.

        Returns
        -------
        BaseOptions
            The unchanged instance when the combination is valid.

        Raises
        ------
        ValueError
            When both *quiet* and *verbose* are ``True``.
        """
        if self.quiet and self.verbose:
            raise ValueError(
                "'quiet' and 'verbose' are mutually exclusive — "
                'pass only one at a time.'
            )
        return self


class InspectOptions(BaseOptions):
    """Options for the ``csvbench inspect`` command.

    Extends :class:`BaseOptions` with the positional *file* argument
    accepted by the inspect command.

    Parameters
    ----------
    file : Path or '-'
        Path to the CSV file to inspect.  Pass ``'-'`` to read from
        stdin (pipe mode).  Existence validation is intentionally
        deferred to the command layer so that error messages can be
        rendered with the Rich formatter.

    Examples
    --------
    >>> InspectOptions(file=Path('data.csv'))
    InspectOptions(file=PosixPath('data.csv'), format='rich', ...)

    >>> InspectOptions(file='-', format='json')
    InspectOptions(file='-', format='json', ...)

    >>> InspectOptions(file=Path('data.csv'), quiet=True, verbose=True)
    ValueError: 'quiet' and 'verbose' are mutually exclusive ...
    """

    file: Path | Literal['-'] = Field(
        description="CSV file to inspect. Use '-' to read from stdin.",
    )