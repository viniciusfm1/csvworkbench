from __future__ import annotations

from typing import Iterator


class RecordSplitter:
    """
    Split raw CSV text into logical records.

    Newlines inside quoted fields are preserved and do not terminate
    records. Handles LF, CRLF, and CR line endings, multiline quoted
    fields, escaped quotes, and malformed EOF inside quotes (recovery
    mode).

    Parameters
    ----------
    quotechar : str, default ``'"'``
        Character used to quote fields.
    preserve_empty_records : bool, default ``True``
        Whether empty records should be emitted.

    Examples
    --------
    >>> splitter = RecordSplitter(quotechar='"')
    >>> list(splitter.split('a,b\\n"c,d",e'))
    ['a,b', '"c,d",e']
    """

    def __init__(
        self,
        quotechar: str,
        preserve_empty_records: bool = True,
    ) -> None:
        self._quotechar = quotechar
        self._preserve_empty_records = preserve_empty_records

    def split(self, text: str) -> Iterator[str]:
            """
            Split raw CSV text into logical CSV records.

            Newlines inside quoted fields are preserved and do not terminate
            records.

            Supports:

            - LF line endings
            - CRLF line endings
            - CR line endings
            - multiline quoted fields
            - escaped quotes
            - malformed EOF inside quotes (recovery mode)

            Parameters
            ----------
            text : str
                Raw decoded file contents.

            quotechar : str
                Quote character.

            preserve_empty_records : bool, default=True
                Whether empty records should be emitted.

            Yields
            ------
            str
                Logical CSV record.
            """

            current_record: list[str] = []

            in_quotes = False

            position = 0

            while position < len(text):

                char = text[position]

                if char == self._quotechar:

                    is_escaped_quote = (
                        in_quotes
                        and position + 1 < len(text)
                        and text[position + 1] == self._quotechar
                    )

                    if is_escaped_quote:

                        current_record.append(self._quotechar)
                        current_record.append(self._quotechar)

                        position += 2

                        continue

                    in_quotes = not in_quotes

                    current_record.append(char)

                    position += 1

                    continue


                newline_size = 0

                if char == '\n':

                    newline_size = 1

                elif char == '\r':

                    newline_size = (
                        2
                        if (
                            position + 1 < len(text)
                            and text[position + 1] == '\n'
                        )
                        else 1
                    )


                found_record_separator = (
                    newline_size > 0
                    and not in_quotes
                )

                if found_record_separator:

                    record = ''.join(current_record)

                    if self._preserve_empty_records or record:

                        yield record

                    current_record = []

                    position += newline_size

                    continue


                current_record.append(char)

                position += 1


            record = ''.join(current_record)

            should_emit_final_record = (
                bool(record)
                or (
                    self._preserve_empty_records
                    and
                    current_record
                )
            )
            if should_emit_final_record:
                yield