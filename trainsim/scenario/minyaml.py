"""A small YAML-subset parser, so scenarios load with nothing installed.

The project has to run on a locked-down machine where ``pip install`` may not be
possible, but scenario files should still be comfortable to hand-edit - which
means comments and block structure, i.e. YAML rather than JSON.

:func:`~trainsim.scenario.loader.read_data_file` uses PyYAML when it is available
and falls back to this parser when it is not. The supported subset is:

* block mappings and block sequences, nested by indentation (spaces only)
* inline flow mappings ``{a: 1, b: two}`` and flow sequences ``[1, 2, 3]``
* ``#`` comments, on their own line or after a value
* scalars: integers, floats, ``true``/``false``, ``null``/``~``, quoted and
  unquoted strings

Not supported, and not used by any shipped scenario: anchors, aliases, tags,
multi-line scalars, multiple documents, and tab indentation.

Write clock times in quotes (``"07:30:00"``). Unquoted they are sexagesimal
integers under YAML 1.1, so PyYAML and this parser would disagree - the test
suite checks the two agree on every shipped scenario.
"""

from typing import Any, List, Tuple


class MiniYamlError(ValueError):
    """Raised when the subset parser cannot make sense of a file."""


def parse(text: str) -> Any:
    """Parse a YAML-subset document into Python data."""
    lines = _tokenize(text)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise MiniYamlError(
            "line %d: unexpected indentation" % (lines[index][2],)
        )
    return value


# --------------------------------------------------------------------- tokenize

def _tokenize(text: str) -> List[Tuple[int, str, int]]:
    """Return ``(indent, content, line_number)`` for every meaningful line."""
    tokens = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise MiniYamlError("line %d: tabs cannot be used for indentation" % number)
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        tokens.append((indent, stripped.strip(), number))
    return tokens


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, respecting quotes."""
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
    return line


# ------------------------------------------------------------------ block parse

def _parse_block(lines, index: int, indent: int):
    if index >= len(lines):
        return None, index
    if lines[index][1].startswith("-"):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines, index: int, indent: int):
    result = {}
    while index < len(lines):
        line_indent, content, number = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise MiniYamlError("line %d: unexpected indentation" % number)
        if content.startswith("-"):
            break

        key, separator, rest = content.partition(":")
        if not separator:
            raise MiniYamlError("line %d: expected 'key: value'" % number)
        key = _parse_scalar(key.strip(), number)
        rest = rest.strip()
        index += 1

        if rest:
            result[key] = _parse_inline(rest, number)
        elif index < len(lines) and lines[index][0] > indent:
            result[key], index = _parse_block(lines, index, lines[index][0])
        elif (index < len(lines) and lines[index][0] == indent
              and lines[index][1].startswith("-")):
            # A sequence may sit at the same indentation as its key.
            result[key], index = _parse_sequence(lines, index, indent)
        else:
            result[key] = None
    return result, index


def _parse_sequence(lines, index: int, indent: int):
    items = []
    while index < len(lines):
        line_indent, content, number = lines[index]
        if line_indent != indent or not content.startswith("-"):
            break

        rest = content[1:]
        offset = len(rest) - len(rest.lstrip(" "))
        item_indent = line_indent + 1 + offset
        rest = rest.strip()
        index += 1

        if not rest:
            if index < len(lines) and lines[index][0] > line_indent:
                value, index = _parse_block(lines, index, lines[index][0])
            else:
                value = None
        elif rest.startswith("{") or rest.startswith("["):
            value = _parse_inline(rest, number)
        elif _looks_like_key(rest):
            # "- key: value" starts a mapping whose remaining keys follow at the
            # column where the key began.
            block = [(item_indent, rest, number)]
            while index < len(lines) and lines[index][0] >= item_indent:
                block.append(lines[index])
                index += 1
            value, consumed = _parse_mapping(block, 0, item_indent)
            if consumed != len(block):
                raise MiniYamlError("line %d: unexpected indentation" % number)
        else:
            value = _parse_scalar(rest, number)
        items.append(value)
    return items, index


def _looks_like_key(text: str) -> bool:
    """True if ``text`` opens a mapping entry rather than being a plain scalar."""
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ":" and (index + 1 == len(text) or text[index + 1] == " "):
            return True
    return False


# ----------------------------------------------------------------- scalar parse

def _parse_inline(text: str, number: int):
    text = text.strip()
    if text.startswith("{"):
        if not text.endswith("}"):
            raise MiniYamlError("line %d: unterminated flow mapping" % number)
        result = {}
        for part in _split_flow(text[1:-1], number):
            if not part.strip():
                continue
            key, sep, value = part.partition(":")
            if not sep:
                raise MiniYamlError(
                    "line %d: expected 'key: value' inside { }" % number
                )
            result[_parse_scalar(key.strip(), number)] = _parse_inline(
                value.strip(), number
            )
        return result
    if text.startswith("["):
        if not text.endswith("]"):
            raise MiniYamlError("line %d: unterminated flow sequence" % number)
        return [
            _parse_inline(part.strip(), number)
            for part in _split_flow(text[1:-1], number)
            if part.strip()
        ]
    return _parse_scalar(text, number)


def _split_flow(text: str, number: int) -> List[str]:
    """Split on commas that are not inside quotes or nested brackets."""
    parts, depth, quote, current = [], 0, None, []
    for char in text:
        if quote:
            if char == quote:
                quote = None
            current.append(char)
            continue
        if char in ("'", '"'):
            quote = char
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth < 0:
                raise MiniYamlError("line %d: unbalanced brackets" % number)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if quote:
        raise MiniYamlError("line %d: unterminated quoted string" % number)
    parts.append("".join(current))
    return parts


_CONSTANTS = {
    "true": True, "True": True, "TRUE": True,
    "false": False, "False": False, "FALSE": False,
    "null": None, "Null": None, "NULL": None, "~": None, "": None,
}


def _parse_scalar(text: str, number: int):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text in _CONSTANTS:
        return _CONSTANTS[text]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text
