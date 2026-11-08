"""Kotlin-specific behaviour of the tree-sitter unused import detector."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_language_pack")

from desloppify.languages._framework.treesitter.analysis.unused_imports import (  # noqa: E402
    detect_unused_imports,
)
from desloppify.languages._framework.treesitter.specs.compiled import KOTLIN_SPEC  # noqa: E402
import textwrap
from desloppify.languages._framework.treesitter.analysis.unused_imports import (
    detect_unused_imports,
)


def _unused(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "Sample.kt"
    path.write_text(source, encoding="utf-8")
    return sorted(entry["name"] for entry in detect_unused_imports([str(path)], KOTLIN_SPEC))


def test_operator_convention_imports_count_as_used(tmp_path: Path) -> None:
    source = """package p

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import com.acme.contains
import com.acme.component1
import com.acme.component2
import com.acme.plus

fun f(items: Set<Int>) {
    var count by mutableStateOf(0)
    val (a, b) = Pair(1, 2)
    if (count in items) count = a + b
}
"""
    assert _unused(tmp_path, source) == []


def test_operator_imports_without_matching_syntax_are_unused(tmp_path: Path) -> None:
    source = """package p

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue

fun f() {
    val count = 1
}
"""
    assert _unused(tmp_path, source) == ["getValue", "setValue"]


def test_set_value_needs_a_var_delegate(tmp_path: Path) -> None:
    source = """package p

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue

fun f(state: State<Int>) {
    val count by state
}
"""
    assert _unused(tmp_path, source) == ["setValue"]


def test_backticked_alias_and_wildcard_imports(tmp_path: Path) -> None:
    source = """package p

import org.mockito.Mockito.`when`
import com.acme.LongName as Short
import com.acme.Unused as AlsoUnused
import com.acme.model.*

fun f() {
    `when`(Short.make()).thenReturn(null)
}
"""
    assert _unused(tmp_path, source) == ["AlsoUnused"]


def test_plain_unused_import_is_still_reported(tmp_path: Path) -> None:
    source = """package p

import com.acme.BuriedGem
import com.acme.Used

fun f(u: Used) = u
"""
    assert _unused(tmp_path, source) == ["BuriedGem"]


def _detect(tmp_path, contents: str, suffix: str = ".kt"):
    source = tmp_path / f"example{suffix}"
    source.write_text(textwrap.dedent(contents).lstrip())
    return detect_unused_imports([str(source)], KOTLIN_SPEC)


@pytest.mark.parametrize("suffix", [".kt", ".kts"])
@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("getValue", "val state by source"),
        ("getValue", "var state by source"),
        ("setValue", "var state by source"),
        ("provideDelegate", "val state by source"),
        ("get", "val selected = devices[name]"),
        ("get", "fun configure() { devices[name] += value }"),
        ("set", "fun configure() { devices[name] = value }"),
        ("set", "fun configure() { devices[name] += value }"),
        ("set", "fun configure() { devices[name]++ }"),
        ("invoke", "fun configure() { devices { create(name) } }"),
        ("invoke", "fun configure() { callback() }"),
        ("assign", "fun configure() { options.target = value }"),
    ],
)
def test_operator_syntax_keeps_potentially_used_imports(tmp_path, suffix, name, body):
    assert _detect(tmp_path, f"import extensions.{name}\n{body}\n", suffix) == []


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("getValue", "val state = source"),
        ("getValue", "class Proxy : Contract by source"),
        ("setValue", "val state by source"),
        ("provideDelegate", "val state = source"),
        ("get", "val selected = devices"),
        ("get", "fun configure() { devices[name] = value }"),
        ("set", "val selected = devices"),
        ("set", "val selected = devices[name]"),
        ("invoke", "val callback = source"),
        ("assign", "val target = value"),
        ("getValue", 'val example = "val state by source"'),
        ("getValue", "// var state by source\nval state = source"),
        ("invoke", 'val example = "callback()"'),
        ("assign", 'val example = "target = value"'),
    ],
)
def test_operator_import_without_matching_syntax_is_unused(tmp_path, name, body):
    findings = _detect(tmp_path, f"import extensions.{name}\n{body}\n")
    assert [entry["name"] for entry in findings] == [name]


def test_ordinary_unused_imports_still_reported_with_delegates(tmp_path):
    findings = _detect(tmp_path, """
        import extensions.getValue
        import extensions.setValue
        import ui.Text
        import ui.WindowWidthSizeClass
        var state by source
    """)
    assert [entry["name"] for entry in findings] == ["Text", "WindowWidthSizeClass"]


def test_operator_import_renamed_to_nonoperator_is_unused(tmp_path):
    findings = _detect(tmp_path, """
        import extensions.getValue as read
        val state by source
    """)
    assert [entry["name"] for entry in findings] == ["read"]


def test_import_renamed_to_operator_can_be_implicitly_used(tmp_path):
    assert _detect(tmp_path, """
        import extensions.invoke as getValue
        val state by source
    """) == []


def test_explicit_operator_call_still_counts(tmp_path):
    assert _detect(tmp_path, """
        import extensions.getValue
        val state = source.getValue(owner, property)
    """) == []
