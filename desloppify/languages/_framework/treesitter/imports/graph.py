"""Shared import graph construction utilities for tree-sitter backends."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from desloppify.base.discovery.file_paths import resolve_path
from desloppify.base.discovery.source import find_source_files
from desloppify.base.search.grep import grep_files

from ..analysis.extractors import _get_parser, _make_query, _run_query, _unwrap_node
from .cache import get_or_parse_tree

if TYPE_CHECKING:
    from desloppify.languages._framework.treesitter import TreeSitterLangSpec


_FRAMEWORK_IMPORT_RE = re.compile(
    r"""(?:from\s+|import\s+)(?:type\s+)?['"]([^'"]+)['"]"""
)
"""Import-specifier extractor for framework files (.astro/.svelte/.vue).

These files mix JS/TS imports with framework-specific syntax that the host
language's tree-sitter grammar can't parse cleanly, so we fall back to a
regex over the raw source. Matches both ``import x from 'y'`` and
``import 'y'`` (with optional ``type`` qualifier)."""


_INLINE_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/|<!--.*?-->")


def _strip_inline_comments(line: str) -> str:
    """Remove single-line JS/HTML comment regions from a source line.

    Applied before regex import extraction so commented-out imports
    (``// import './foo'``, ``/* import 'x' */``, ``<!-- import 'y' -->``)
    don't produce false-positive importer edges and mask genuine orphans.
    Multi-line block comments aren't detected — grep_files yields one row
    per matched line, so mid-block context isn't reconstructable here.
    """
    return _INLINE_COMMENT_RE.sub("", line)


def _path_key(filepath: str) -> str:
    """Normalise a path for identity comparison across relative/absolute forms.

    normcase folds case and separators on Windows and is a no-op elsewhere.
    """
    return os.path.normcase(os.path.abspath(filepath))


def ts_build_dep_graph(
    path: Path,
    spec: TreeSitterLangSpec,
    file_list: list[str],
    *,
    framework_extensions: tuple[str, ...] | None = None,
    framework_file_finder: Callable[[Path], list[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a dependency graph by parsing imports with tree-sitter.

    Returns the same shape as Python/TS dep graphs:
    {file: {"imports": set[str], "importers": set[str], "import_count": int, "importer_count": int}}

    When ``framework_extensions`` is provided (e.g. ``(".astro", ".svelte",
    ".vue")``), files under ``path`` with those extensions are also scanned
    via a regex-based import extractor, and their imports are recorded as
    importer edges on matching entries in ``file_list``. The framework files
    themselves are intentionally not added as graph nodes — they don't belong
    to the host language's extension set, so we never want them to surface in
    orphan or coupling reports.

    When ``framework_file_finder`` is provided, it's used to enumerate
    framework files (so callers can supply an exclude-aware finder built via
    ``make_file_finder``). When omitted, a plain ``find_source_files`` scan
    is used — convenient for unit tests but doesn't honor user-configured
    exclusions; production callers should pass a finder.
    """
    if not spec.import_query or not spec.resolve_import:
        return {}

    parser, language = _get_parser(spec.grammar)
    if spec.grammar == "kotlin":
        from .kotlin import build_kotlin_graph

        return build_kotlin_graph(file_list, parser)

    query = _make_query(language, spec.import_query)

    scan_path = str(path.resolve())
    file_keys = {_path_key(filepath): filepath for filepath in file_list}
    # Discovery may also return paths relative to the scan root rather than
    # the current directory; index that form too without overriding cwd keys.
    for filepath in file_list:
        if not os.path.isabs(filepath):
            file_keys.setdefault(
                _path_key(os.path.join(scan_path, filepath)), filepath
            )
    graph: dict[str, dict[str, Any]] = {}

    # Initialize all files in the graph.
    for f in absolute_file_list:
        graph[f] = {"imports": set(), "importers": set()}

    for filepath in file_list:
        cached = get_or_parse_tree(filepath, parser, spec.grammar)
        if cached is None:
            continue
        _source, tree = cached
        matches = _run_query(query, tree.root_node)

        for _pattern_idx, captures in matches:
            path_node = _unwrap_node(captures.get("path"))
            if not path_node:
                continue

            raw_text = path_node.text
            import_text = (
                raw_text.decode("utf-8", errors="replace")
                if isinstance(raw_text, bytes)
                else str(raw_text)
            )

            # Strip surrounding quotes if present.
            import_text = import_text.strip("\"'`")

            # Prepend group-use prefix when present (PHP ``use A\B\{C, D}``).
            prefix_node = _unwrap_node(captures.get("prefix"))
            if prefix_node is not None:
                prefix_raw = prefix_node.text
                prefix_text = (
                    prefix_raw.decode("utf-8", errors="replace")
                    if isinstance(prefix_raw, bytes)
                    else str(prefix_raw)
                ).strip("\"'`")
                import_text = f"{prefix_text}\\{import_text}"

            resolved = spec.resolve_import(import_text, filepath, scan_path)
            if resolved is None:
                continue

            # Resolvers may return project-relative, scan-relative, or absolute
            # paths. Match in one path space, retaining the discovered graph keys.
            resolved_key = file_keys.get(_path_key(resolved))
            if resolved_key is None and not os.path.isabs(resolved):
                resolved_key = file_keys.get(
                    _path_key(os.path.join(scan_path, resolved))
                )
            if resolved_key is None:
                continue

            graph[filepath]["imports"].add(resolved_key)
            graph[resolved_key]["importers"].add(filepath)

    if framework_extensions:
        _add_framework_importers(
            graph=graph,
            file_keys=file_keys,
            framework_extensions=framework_extensions,
            framework_file_finder=framework_file_finder,
            spec=spec,
            scan_path=scan_path,
            path=path,
        )

    # Finalize: add counts.
    for data in graph.values():
        data["import_count"] = len(data["imports"])
        data["importer_count"] = len(data["importers"])

    return graph


def _add_framework_importers(
    *,
    graph: dict[str, dict[str, Any]],
    file_keys: dict[str, str],
    framework_extensions: tuple[str, ...],
    framework_file_finder: Callable[[Path], list[str]] | None,
    spec: TreeSitterLangSpec,
    scan_path: str,
    path: Path,
) -> None:
    """Add framework files (.astro/.svelte/.vue) as importer edges on graph nodes.

    Framework files carry their imports in fenced or top-level sections that
    the host language's tree-sitter grammar can't parse cleanly. We extract
    import specifiers with a regex and resolve them via the spec's own
    ``resolve_import`` so framework-file imports behave exactly like
    host-language imports — only edges into ``file_set`` are kept, and the
    framework files themselves are not added as graph nodes.
    """
    if framework_file_finder is not None:
        fw_files = framework_file_finder(path)
    else:
        fw_files = find_source_files(path, list(framework_extensions))
    if not fw_files:
        return

    # grep_files yields one row per matched line, so resolving each filepath
    # to absolute inside the loop would re-do the work N times per file.
    # Build the abs-path map once up front.
    fw_abs = {f: resolve_path(f) for f in fw_files}

    for filepath, _lineno, line in grep_files(
        r"""(?:\bfrom\s+['"]|\bimport\s+['"])""", fw_files
    ):
        importer_abs = fw_abs[filepath]
        cleaned_line = _strip_inline_comments(line)
        for match in _FRAMEWORK_IMPORT_RE.finditer(cleaned_line):
            import_text = match.group(1)
            resolved = spec.resolve_import(import_text, importer_abs, scan_path)
            if resolved is None:
                continue
            if not os.path.isabs(resolved):
                resolved = os.path.normpath(os.path.join(scan_path, resolved))
            key = file_keys.get(_path_key(resolved))
            if key is None:
                continue
            graph[key]["importers"].add(importer_abs)


def make_ts_dep_builder(
    spec: TreeSitterLangSpec,
    file_finder: Callable[[Path], list[str]],
    *,
    framework_extensions: tuple[str, ...] | None = None,
    framework_file_finder: Callable[[Path], list[str]] | None = None,
) -> Callable[[Path], dict[str, dict[str, Any]]]:
    """Create a dep graph builder bound to a TreeSitterLangSpec + file finder.

    Returns a callable with signature (path: Path) -> dict,
    matching the contract expected by LangConfig.build_dep_graph.

    When ``framework_extensions`` is provided, framework files under the
    scanned path also contribute importer edges (see ``ts_build_dep_graph``).
    ``framework_file_finder`` lets callers thread the same exclude set used
    for the host language; when omitted, the framework scan honors only
    default exclusions.
    """

    def build(path: Path) -> dict[str, dict[str, Any]]:
        file_list = file_finder(path)
        return ts_build_dep_graph(
            path,
            spec,
            file_list,
            framework_extensions=framework_extensions,
            framework_file_finder=framework_file_finder,
        )

    return build


__all__ = ["make_ts_dep_builder", "ts_build_dep_graph"]
