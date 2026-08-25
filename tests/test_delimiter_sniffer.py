from __future__ import annotations

from csvbench.core.detectors.delimiter import DelimiterDetector
from csvbench.core.parser.record_splitter import RecordSplitter
from csvbench.core.sniffer import DelimiterSniffer


def _client_style_csv() -> str:
    """Semicolon CSV with quoted notes that contain newlines and commas."""
    header = 'id;name;city;notes'
    rows = []
    for i in range(12):
        notes = (
            f'"Visit {i}, confirmed\n'
            f'follow-up needed, see file {i}, notes\n'
            f'comma, comma, comma"'
        )
        rows.append(f'{i};Name{i};City{i};{notes}')
    return header + '\n' + '\n'.join(rows) + '\n'


def _records(sample: str) -> list[str]:
    return [
        record
        for record in RecordSplitter(quotechar='"').split(sample)
        if record.strip()
    ]


def test_sniff_semicolon_csv_with_quoted_embedded_newlines_and_commas() -> None:
    result = DelimiterSniffer().sniff(_client_style_csv())
    assert result.sep == ';'


def test_sniff_comma_csv() -> None:
    sample = 'id,name,city\n1,Alice,SP\n2,Bob,RJ\n3,Carol,MG\n'
    result = DelimiterSniffer().sniff(sample)
    assert result.sep == ','


def test_sniff_two_column_comma_csv() -> None:
    result = DelimiterSniffer().sniff('a,b\n1,2\n3,4\n')
    assert result.sep == ','


def test_sniff_tab_csv() -> None:
    sample = 'id\tname\tcity\n1\tAlice\tSP\n2\tBob\tRJ\n'
    result = DelimiterSniffer().sniff(sample)
    assert result.sep == '\t'


def test_quoting_score_unused_candidate_is_zero() -> None:
    sniffer = DelimiterSniffer()
    lines = ['a;b;c', '1;2;3', '4;5;6']
    assert sniffer._quoting_score(lines, '|') == 0.0
    assert sniffer._quoting_score(lines, '\t') == 0.0
    assert sniffer._quoting_score(lines, '||') == 0.0


def test_unused_candidate_cannot_win() -> None:
    sniffer = DelimiterSniffer()
    sample = 'a;b;c\n1;2;3\n4;5;6\n'
    records = _records(sample)
    semicolon = sniffer._score_candidate(records, ';')
    pipe = sniffer._score_candidate(records, '|')
    tab = sniffer._score_candidate(records, '\t')

    assert pipe.total == 0.0
    assert tab.total == 0.0
    assert semicolon.total > pipe.total
    assert sniffer.sniff(sample).sep == ';'


def test_position_score_insufficient_occurrences_is_zero() -> None:
    sniffer = DelimiterSniffer()
    assert sniffer._position_score(['a,b,c'], ',') == 0.0


def test_detect_semicolon_file_with_multiline_quoted_fields(tmp_path) -> None:
    path = tmp_path / 'clientes_style.csv'
    path.write_text(_client_style_csv(), encoding='utf-8')
    result = DelimiterDetector().detect(path, encoding='utf-8')
    assert result.sep == ';'


def test_detect_comma_file(tmp_path) -> None:
    path = tmp_path / 'comma.csv'
    path.write_text('id,name,city\n1,Alice,SP\n2,Bob,RJ\n', encoding='utf-8')
    result = DelimiterDetector().detect(path, encoding='utf-8')
    assert result.sep == ','


def test_detect_tab_file(tmp_path) -> None:
    path = tmp_path / 'tab.csv'
    path.write_text('id\tname\tcity\n1\tAlice\tSP\n2\tBob\tRJ\n', encoding='utf-8')
    result = DelimiterDetector().detect(path, encoding='utf-8')
    assert result.sep == '\t'
