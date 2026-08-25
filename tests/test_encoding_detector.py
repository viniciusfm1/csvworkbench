from __future__ import annotations

from pathlib import Path

import pytest

from csvbench.core.detectors.encoding import EncodingDetector

_CLIENTES = Path('/home/vinicius/workspace/data/mayara_sleumer/Clientes.csv')


def test_utf8_with_accents(tmp_path: Path) -> None:
    path = tmp_path / 'utf8.csv'
    path.write_bytes('Código;Observações;ação\n1;2;3\n'.encode('utf-8'))
    result = EncodingDetector().detect(path)
    assert result.name == 'utf-8'
    assert result.method == 'utf8'
    assert result.confidence == 1.0


def test_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / 'bom.csv'
    path.write_bytes(b'\xef\xbb\xbfid,name\n1,Alice\n')
    result = EncodingDetector().detect(path)
    assert result.name == 'utf-8-sig'
    assert result.method == 'bom'
    assert result.bom_detected is True


def test_ascii_is_utf8(tmp_path: Path) -> None:
    path = tmp_path / 'ascii.csv'
    path.write_text('id,name\n1,Alice\n', encoding='ascii')
    result = EncodingDetector().detect(path)
    assert result.name == 'utf-8'


def test_iso8859_1_portuguese_not_cp1250(tmp_path: Path) -> None:
    text = (
        'Código;Endereço;Observações;ação;mãe;número\n'
        '1;São Paulo;não;confirmação;João;10\n'
        '2;Belo Horizonte;útil;informação;José;20\n'
    )
    path = tmp_path / 'latin1.csv'
    path.write_bytes(text.encode('iso-8859-1'))
    result = EncodingDetector().detect(path)
    assert result.name == 'iso-8859-1'
    assert result.name != 'windows-1250'
    assert result.confidence < 1.0


def test_windows1252_euro_and_quotes(tmp_path: Path) -> None:
    text = 'Preço;nota\n10€;“ok”\n'
    path = tmp_path / 'cp1252.csv'
    path.write_bytes(text.encode('cp1252'))
    result = EncodingDetector().detect(path)
    assert result.name == 'windows-1252'


def test_windows1250_polish_not_western(tmp_path: Path) -> None:
    text = 'imię;miasto\nZażółć gęślą jaźń;Łódź\nBąk;Kraków\n'
    path = tmp_path / 'cp1250.csv'
    path.write_bytes(text.encode('cp1250'))
    result = EncodingDetector().detect(path)
    assert result.name in {'windows-1250', 'iso-8859-2'}
    assert result.name not in {'iso-8859-1', 'windows-1252'}


@pytest.mark.skipif(not _CLIENTES.exists(), reason='local Clientes.csv fixture is absent')
def test_clientes_csv_iso8859_1() -> None:
    result = EncodingDetector().detect(_CLIENTES)
    assert result.name == 'iso-8859-1'
