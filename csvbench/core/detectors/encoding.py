from __future__ import annotations

import codecs
from pathlib import Path
from typing import Any, Literal

import chardet
from charset_normalizer import from_bytes
from pydantic import BaseModel, Field

_BOM_MAP: dict[bytes, str] = {
    b'\xef\xbb\xbf':     'utf-8-sig',
    b'\x00\x00\xfe\xff': 'utf-32-be',
    b'\xff\xfe\x00\x00': 'utf-32-le',
    b'\xff\xfe':         'utf-16-le',
    b'\xfe\xff':         'utf-16-be',
}

_CHAOS_TIE_TOLERANCE = 0.005
_ENSEMBLE_CONFIDENCE_STRONG = 0.90
_ENSEMBLE_CONFIDENCE_TIE = 0.82

_WESTERN_LANGUAGES = {
    'pt', 'es', 'fr', 'it', 'de', 'ca', 'nl', 'en',
    'da', 'sv', 'no', 'nb', 'nn', 'fi', 'is', 'gl', 'eu',
}
_CENTRAL_LANGUAGES = {'pl', 'cs', 'sk', 'hu', 'hr', 'sl', 'ro', 'sr', 'bs'}

# Bytes whose latin-1 / cp1252 letter differs from cp1250.
_WESTERN_MARKER_BYTES = (0xE3, 0xC3, 0xF5, 0xD5, 0xE0)  # ã Ã õ Õ à
# Bytes that are Polish/Central letters in cp1250 and symbols in cp1252.
_CENTRAL_MARKER_BYTES = (0xA5, 0xB9, 0xA3, 0xB3, 0xC6, 0xE6, 0xAF, 0xBF)
# Typical Windows-1252 punctuation in the C1 range (absent from ISO-8859-1 text).
_CP1252_C1_BYTES = (0x80, 0x91, 0x92, 0x93, 0x94, 0x96, 0x97)

_WESTERN_CODECS = {'iso8859-1', 'iso8859-15', 'cp1252'}
_CENTRAL_CODECS = {'cp1250', 'iso8859-2', 'cp1257', 'iso8859-13'}

_REPORT_NAMES = {
    'iso8859-1': 'iso-8859-1',
    'iso8859-2': 'iso-8859-2',
    'iso8859-15': 'iso-8859-15',
    'cp1252': 'windows-1252',
    'cp1250': 'windows-1250',
    'cp1251': 'windows-1251',
    'cp1253': 'windows-1253',
    'cp1254': 'windows-1254',
    'cp1257': 'windows-1257',
    'utf-8': 'utf-8',
    'utf-8-sig': 'utf-8-sig',
    'ascii': 'utf-8',
}

EncodingMethod = Literal[
    'bom',
    'utf8',
    'ensemble',
    'charset_normalizer',
    'chardet',
    'fallback',
    'override',
]


class EncodingResult(BaseModel):
    """
    Outcome of encoding detection.

    Parameters
    ----------
    name : str
        Canonical encoding name (e.g. ``'utf-8'``, ``'iso-8859-1'``).
    confidence : float
        Detection confidence in the range ``[0.0, 1.0]``.
        Values below 1.0 mean more than one 8-bit code page was plausible.
    bom_detected : bool
        ``True`` when a byte-order mark was found and stripped.
    method : str
        Which stage produced this result.

    Examples
    --------
    >>> result = EncodingResult(name='utf-8', confidence=1.0, method='utf8')
    >>> result.name
    'utf-8'
    """

    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bom_detected: bool = False
    method: EncodingMethod


class EncodingDetector:
    def __init__(
        self,
        sample_size: int = 32768,
        default_fallback: str = 'cp1252',
    ) -> None:
        self.sample_size = sample_size
        self.default_fallback = default_fallback

    def detect(self, path: Path | str) -> EncodingResult:
        """
        Detect the encoding of *path*.

        BOM and a strict UTF-8 probe run first. charset-normalizer and
        chardet then vote; 8-bit ties (``cp1250`` vs ``iso-8859-1``)
        are broken with language and byte-fingerprint signals.

        Parameters
        ----------
        path : Path or str
            File to inspect.

        Returns
        -------
        EncodingResult
            Detected encoding, confidence, and detection method.
        """
        path = Path(path)
        raw = path.read_bytes()[: self.sample_size]

        return (
            self._check_bom(raw)
            or self._try_utf8(raw)
            or self._resolve(raw)
        )

    def _check_bom(self, raw: bytes) -> EncodingResult | None:
        """Return a result when *raw* starts with a known BOM."""
        for bom, encoding in _BOM_MAP.items():
            if raw.startswith(bom):
                return EncodingResult(
                    name=encoding,
                    confidence=1.0,
                    bom_detected=True,
                    method='bom',
                )
        return None

    def _try_utf8(self, raw: bytes) -> EncodingResult | None:
        """Return UTF-8 when *raw* decodes with no errors."""
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError:
            return None
        return EncodingResult(name='utf-8', confidence=1.0, method='utf8')

    def _resolve(self, raw: bytes) -> EncodingResult:
        """Combine charset-normalizer matches with chardet language/vote."""
        cn_matches = list(from_bytes(raw))
        chardet_result = chardet.detect(
            raw,
            no_match_encoding=self.default_fallback,
        )

        chardet_codec = _codec_name(chardet_result.get('encoding'))
        chardet_lang = _language_code(chardet_result.get('language'))
        chardet_confidence = float(chardet_result.get('confidence') or 0.0)

        if not cn_matches:
            return self._from_chardet_only(
                raw,
                chardet_codec,
                chardet_lang,
                chardet_confidence,
            )

        min_chaos = min(match.chaos for match in cn_matches)
        tied = [
            match
            for match in cn_matches
            if match.chaos <= min_chaos + _CHAOS_TIE_TOLERANCE
        ]
        tied_codecs = [_codec_name(match.encoding) for match in tied]
        tied_codecs = [codec for codec in tied_codecs if codec]

        family = _preferred_family(raw, chardet_lang)
        resolved = _resolve_8bit_name(raw, family, tied_codecs)

        if resolved is not None:
            strong = family is not None and (
                _marker_counts(raw)[0] >= 3 or _marker_counts(raw)[1] >= 3
            )
            confidence = (
                _ENSEMBLE_CONFIDENCE_STRONG
                if strong
                else _ENSEMBLE_CONFIDENCE_TIE
            )
            if len(tied) == 1 and _report_name(tied_codecs[0]) == resolved:
                confidence = round(1.0 - tied[0].chaos, 4)
                method: EncodingMethod = 'charset_normalizer'
            else:
                method = 'ensemble'
            return EncodingResult(
                name=resolved,
                confidence=confidence,
                method=method,
            )

        best = min(tied, key=lambda match: match.chaos)
        return EncodingResult(
            name=_report_name(_codec_name(best.encoding) or best.encoding),
            confidence=round(1.0 - best.chaos, 4),
            method='charset_normalizer',
        )

    def _from_chardet_only(
        self,
        raw: bytes,
        chardet_codec: str | None,
        chardet_lang: str,
        chardet_confidence: float,
    ) -> EncodingResult:
        """Fallback when charset-normalizer yields no matches."""
        family = _preferred_family(raw, chardet_lang)
        resolved = _resolve_8bit_name(
            raw,
            family,
            [chardet_codec] if chardet_codec else [],
        )
        if resolved is not None:
            return EncodingResult(
                name=resolved,
                confidence=_ENSEMBLE_CONFIDENCE_TIE,
                method='ensemble',
            )

        if chardet_codec:
            method: EncodingMethod = (
                'fallback'
                if (
                    chardet_codec == _codec_name(self.default_fallback)
                    and chardet_confidence < 0.05
                )
                else 'chardet'
            )
            return EncodingResult(
                name=_report_name(chardet_codec),
                confidence=min(max(chardet_confidence, 0.0), 1.0),
                method=method,
            )

        return EncodingResult(
            name=_report_name(_codec_name(self.default_fallback) or 'cp1252'),
            confidence=0.05,
            method='fallback',
        )


def _codec_name(name: str | None) -> str | None:
    """Return the Python codec name, or ``None`` when *name* is empty."""
    if not name:
        return None
    try:
        return codecs.lookup(name).name
    except LookupError:
        return name.strip().lower().replace('_', '-')


def _report_name(codec: str) -> str:
    """Map a Python codec name to a stable IANA-style label."""
    return _REPORT_NAMES.get(codec, codec.replace('_', '-'))


def _language_code(language: Any) -> str:
    """Normalise chardet language to a lowercase ISO-like code."""
    if not language:
        return ''
    text = str(language).strip().lower()
    if not text:
        return ''
    return text.split('-', 1)[0][:2]


def _marker_counts(raw: bytes) -> tuple[int, int]:
    """Return (western_marker_count, central_marker_count) for *raw*."""
    western = sum(raw.count(bytes([byte])) for byte in _WESTERN_MARKER_BYTES)
    central = sum(raw.count(bytes([byte])) for byte in _CENTRAL_MARKER_BYTES)
    return western, central


def _has_cp1252_c1(raw: bytes) -> bool:
    """Return True when typical Windows-1252 C1 punctuation is present."""
    present = set(raw)
    return any(byte in present for byte in _CP1252_C1_BYTES)


def _preferred_family(raw: bytes, language: str) -> str | None:
    """Infer western vs central-european family from bytes and language."""
    western, central = _marker_counts(raw)

    if western >= 3 and western > central * 2:
        return 'western'
    if central >= 3 and central > western * 2:
        return 'central'

    if language in _WESTERN_LANGUAGES and central == 0:
        return 'western'
    if language in _CENTRAL_LANGUAGES and western == 0 and not _has_cp1252_c1(raw):
        return 'central'

    if western > central:
        return 'western'
    if central > western:
        return 'central'
    return None


def _resolve_8bit_name(
    raw: bytes,
    family: str | None,
    tied_codecs: list[str],
) -> str | None:
    """Pick iso-8859-1 / windows-1252 / windows-1250 from a tied 8-bit set."""
    western, central = _marker_counts(raw)
    has_c1 = _has_cp1252_c1(raw)
    tied = set(tied_codecs)

    if family is None and not has_c1 and western == 0 and central == 0:
        if tied & _WESTERN_CODECS and tied & _CENTRAL_CODECS:
            family = 'western'

    if family is None and has_c1 and central == 0:
        return 'windows-1252'

    if family == 'western':
        return 'windows-1252' if has_c1 else 'iso-8859-1'

    if family == 'central':
        if 'iso8859-2' in tied and not has_c1:
            return 'iso-8859-2'
        return 'windows-1250'

    return None
