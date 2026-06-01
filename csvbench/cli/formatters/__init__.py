from __future__ import annotations

from pathlib import Path

from csvbench.cli.formatters.base import BaseFormatter
from csvbench.cli.formatters.rich_formatter import RichFormatter
from csvbench.cli.formatters.json_formatter import JsonFormatter


def get_formatter(
    format: str,  # noqa: A002
    output: Path | None = None,
    quiet: bool = False,
    verbose: bool = False,
) -> BaseFormatter:
    """Instantiate and return the appropriate formatter.

    Acts as the single entry point for formatter construction across all
    commands.  Commands import only ``get_formatter`` — never the
    concrete formatter classes — so swapping or extending formatters
    requires no changes outside this module.

    Parameters
    ----------
    format : {'rich', 'json'}
        Desired output format.
    output : Path or None
        Optional file path for JSON output.  Ignored by
        :class:`~csvbench.cli.formatters.rich_fmt.RichFormatter`.
    quiet : bool
        Suppress full output in favour of a single summary line.
    verbose : bool
        Emit extended detail.

    Returns
    -------
    BaseFormatter
        A fully constructed formatter ready to call ``render`` on.

    Raises
    ------
    ValueError
        If *format* is not a recognised format string.

    Examples
    --------
    >>> fmt = get_formatter('rich')
    >>> fmt = get_formatter('json', output=Path('report.json'))
    >>> fmt = get_formatter('rich', quiet=True)
    """
    _registry: dict[str, type[BaseFormatter]] = {
        'rich': RichFormatter,
        'json': JsonFormatter,
    }

    formatter_cls = _registry.get(format)

    if formatter_cls is None:
        supported = ', '.join(f"'{k}'" for k in _registry)
        raise ValueError(
            f"Unknown format {format!r}. Supported formats: {supported}."
        )

    return formatter_cls(output=output, quiet=quiet, verbose=verbose)


__all__ = ['get_formatter', 'BaseFormatter', 'RichFormatter', 'JsonFormatter']
