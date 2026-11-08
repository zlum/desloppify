"""Shared tree-sitter spec types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TreeSitterLangSpec:
    """Per-language tree-sitter configuration."""

    grammar: str
    function_query: str
    comment_node_types: frozenset[str]
    string_node_types: frozenset[str] = frozenset()

    import_query: str = ""
    resolve_import: Callable[[str, str, str], str | None] | None = None
    # (imported name, regex) pairs: an import whose name never appears in the
    # file still counts as used when the regex matches, e.g. Kotlin operator
    # conventions (`getValue` is called by `by`, `contains` by `in`).
    implicit_import_uses: tuple[tuple[str, str], ...] = ()

    # Imported names whose usage a language invokes implicitly by convention
    # (e.g. Kotlin operator/property-delegation functions). A textual
    # reference search cannot rule these out, so unused-import detection
    # must skip them to avoid false positives.
    implicit_import_names: frozenset[str] = frozenset()

    # Returns the binding an import node introduces (name plus the statement
    # that declares it), or None when it binds nothing. Set it for languages
    # where an import is an ordinary expression that may be assigned to any
    # name, so unused-import detection reads the binding rather than guessing
    # from the module path.
    import_binding: Callable[[Any], Any | None] | None = None

    class_query: str = ""

    log_patterns: tuple[str, ...] = (
        r"^\s*(?:fmt\.Print|log\.)",
        r"^\s*(?:println!|eprintln!|dbg!)",
        r"^\s*(?:puts |p |pp )",
        r"^\s*(?:print\(|NSLog)",
        r"^\s*(?:System\.out\.|Logger\.)",
        r"^\s*console\.",
    )


__all__ = ["TreeSitterLangSpec"]
