from __future__ import annotations


class FieldSplitter:
    """
    Split a single CSV record into a list of field values.

    Iterates over the record character by character, tracking whether
    the current position is inside a quoted field. The separator is
    matched with :meth:`str.find` so that multi-character separators
    are handled without any regular-expression overhead.

    Parameters
    ----------
    sep : str
        Field separator (single- or multi-character).
    quotechar : str, default ``'"'``
        Character used to quote fields.

    Examples
    --------
    >>> splitter = FieldSplitter(sep=',')
    >>> splitter.split('hello,"world, foo",bar')
    ['hello', 'world, foo', 'bar']
    """

    def __init__(self, sep: str, quotechar: str) -> None:
        self._sep = sep
        self._sep_len = len(sep)
        self._quotechar = quotechar

    def split(self, line: str) -> list[str]:
        """
        Parse *line* into an ordered list of field values.

        Escaped quotes (``quotechar`` repeated twice, per RFC 4180) are
        collapsed to a single ``quotechar`` in the returned values.
        The outer quote characters of quoted fields are stripped.

        Parameters
        ----------
        line : str
            A single logical record from the source file.

        Returns
        -------
        list of str
            Ordered list of field values extracted from *line*.
        """
        if line is None:
            raise TypeError(
                f'split() expected a str, got None. '
                f'Check that the line reader is not passing empty iterator results.'
            )

        sep = self._sep
        sep_len = self._sep_len
        quotechar = self._quotechar
        fields: list[str] = []
        current_field: list[str] = []
        in_quotes = False
        position = 0
        line_len = len(line)

        while position < line_len:
            char = line[position]

            if char == quotechar:
                is_escaped_quote = (
                    in_quotes
                    and position + 1 < line_len
                    and line[position + 1] == quotechar
                )
                if is_escaped_quote:
                    current_field.append(quotechar)
                    position += 2
                    continue

                in_quotes = not in_quotes
                position += 1
                continue

            if not in_quotes:
                if line.find(sep, position, position + sep_len) == position:
                    fields.append(''.join(current_field))
                    current_field = []
                    position += sep_len
                    continue

            current_field.append(char)
            position += 1

        fields.append(''.join(current_field))
        return fields