from __future__ import annotations

import json
from pathlib import Path

from desloppify.languages.cxx._helpers import build_cxx_dep_graph


def _write(root: Path, rel_path: str, content: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def test_build_dep_graph_from_compile_commands(tmp_path):
    source = _write(
        tmp_path,
        "src/main.cpp",
        '#include "generated.hpp"\nint main() { return 0; }\n',
    )
    header = _write(tmp_path, "generated/generated.hpp", "#pragma once\n")
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(tmp_path),
                    "file": "src/main.cpp",
                    "command": "clang++ -Igenerated -c src/main.cpp",
                }
            ]
        )
    )

    graph = build_cxx_dep_graph(tmp_path)

    assert str(source.resolve()) in graph
    assert str(header.resolve()) in graph[str(source.resolve())]["imports"]

def test_build_dep_graph_distinguishes_angle_vs_quoted_include_resolution(tmp_path):
    source = _write(
        tmp_path,
        "src/main.cpp",
        '#include <widget.hpp>\n#include "widget_local.hpp"\nint main() { return answer() + local_answer(); }\n',
    )
    local_header = _write(
        tmp_path,
        "src/widget_local.hpp",
        "#pragma once\ninline int local_answer() { return 1; }\n",
    )
    include_header = _write(
        tmp_path,
        "include/widget.hpp",
        "#pragma once\ninline int answer() { return 42; }\n",
    )
    _write(
        tmp_path,
        "src/widget.hpp",
        "#pragma once\ninline int answer() { return -1; }\n",
    )
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(tmp_path),
                    "file": "src/main.cpp",
                    "command": "clang++ -Iinclude -c src/main.cpp",
                }
            ]
        )
    )

    graph = build_cxx_dep_graph(tmp_path)

    imports = graph[str(source.resolve())]["imports"]
    assert str(include_header.resolve()) in imports
    assert str(local_header.resolve()) in imports
    assert str((tmp_path / "src" / "widget.hpp").resolve()) not in imports


def test_compile_database_marks_only_actual_translation_unit_roots(tmp_path):
    compiled = _write(tmp_path, "compiled/unit.cpp", "int compiled() { return 1; }\n")
    unused = _write(tmp_path, "unused/unit.cpp", "int unused() { return 0; }\n")
    header = _write(tmp_path, "include/pch.hpp", "#pragma once\n")
    malformed = _write(tmp_path, "missing-command.cpp", "int missing() { return 0; }\n")
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": str(compiled), "arguments": ["clang++", "-c", str(compiled)]},
        {"directory": str(tmp_path), "file": str(header), "command": f"clang++ -x c++-header {header}"},
        {"directory": str(tmp_path), "file": str(malformed)},
    ]))
    graph = build_cxx_dep_graph(tmp_path)
    assert graph[str(compiled.resolve())]["is_entry_point"] is True
    for path in (unused, header, malformed):
        assert not graph[str(path.resolve())].get("is_entry_point", False)


def test_compile_database_expands_response_files_and_follows_header_includes(tmp_path):
    source = _write(tmp_path, "src/unit.cpp", '#include "Public/api.hpp"\n')
    public = _write(
        tmp_path, "module/Public/api.hpp", '#include "Detail/implementation.hpp"\n'
    )
    detail = _write(
        tmp_path, "module/Detail/implementation.hpp", '#include "Public/api.hpp"\n'
    )
    (tmp_path / "nested.rsp").write_text('-I "module"')
    (tmp_path / "compile.rsp").write_text("@nested.rsp -c src/unit.cpp")
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(tmp_path),
                    "file": str(source),
                    "command": "clang++ @compile.rsp",
                },
            ]
        )
    )
    graph = build_cxx_dep_graph(tmp_path)
    assert graph[str(source.resolve())]["imports"] == {str(public.resolve())}
    assert graph[str(public.resolve())]["imports"] == {str(detail.resolve())}
    assert graph[str(detail.resolve())]["imports"] == {str(public.resolve())}


def test_response_file_cycles_and_missing_files_do_not_invent_includes(tmp_path):
    from desloppify.languages.cxx.detectors.deps import _parse_command_tokens

    (tmp_path / "a.rsp").write_text("@b.rsp -Iinclude")
    (tmp_path / "b.rsp").write_text("@a.rsp -DVALUE=1")
    tokens = _parse_command_tokens(
        {"directory": str(tmp_path), "arguments": ["clang++", "@a.rsp", "@missing.rsp"]}
    )
    assert tokens == ["clang++", "-DVALUE=1", "-Iinclude", "@missing.rsp"]


def test_shared_header_keeps_each_translation_units_include_context(tmp_path):
    first = _write(tmp_path, "first.cpp", '#include "api.hpp"\n')
    second = _write(tmp_path, "second.cpp", '#include "api.hpp"\n')
    public = _write(tmp_path, "common/api.hpp", "#include <config.hpp>\n")
    first_config = _write(tmp_path, "one/config.hpp", "#pragma once\n")
    second_config = _write(tmp_path, "two/config.hpp", "#pragma once\n")
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(tmp_path),
                    "file": str(first),
                    "arguments": ["clang++", "-Icommon", "-Ione", "-c", str(first)],
                },
                {
                    "directory": str(tmp_path),
                    "file": str(second),
                    "arguments": ["clang++", "-Icommon", "-Itwo", "-c", str(second)],
                },
            ]
        )
    )
    graph = build_cxx_dep_graph(tmp_path)
    assert graph[str(public.resolve())]["imports"] == {
        str(first_config.resolve()),
        str(second_config.resolve()),
    }


def test_compile_database_traverses_header_dependencies(tmp_path):
    source = _write(tmp_path, "src/main.cpp", '#include <api.hpp>\n')
    api = _write(tmp_path, "include/api.hpp", '#include "detail.hpp"\n')
    detail = _write(tmp_path, "include/detail.hpp", "#pragma once\n")
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": str(source), "command": "clang++ -Iinclude -c src/main.cpp"},
    ]))
    graph = build_cxx_dep_graph(tmp_path)
    assert str(detail) in graph[str(api)]["imports"]
    assert graph[str(detail)]["importers"] == {str(api)}


def test_compile_database_header_cycle_terminates(tmp_path):
    source = _write(tmp_path, "src/main.cpp", '#include <a.hpp>\n')
    first = _write(tmp_path, "include/a.hpp", '#include "b.hpp"\n')
    second = _write(tmp_path, "include/b.hpp", '#include "a.hpp"\n')
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": str(source), "command": "clang++ -Iinclude -c src/main.cpp"},
    ]))
    graph = build_cxx_dep_graph(tmp_path)
    assert graph[str(first)]["imports"] == {str(second)}
    assert graph[str(second)]["imports"] == {str(first)}


def test_compile_database_expands_headers_in_each_include_context(tmp_path):
    first = _write(tmp_path, "src/first.cpp", '#include <shared.hpp>\n')
    second = _write(tmp_path, "src/second.cpp", '#include <shared.hpp>\n')
    shared = _write(tmp_path, "common/shared.hpp", '#include <variant.hpp>\n')
    first_variant = _write(tmp_path, "first/variant.hpp", "#pragma once\n")
    second_variant = _write(tmp_path, "second/variant.hpp", "#pragma once\n")
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": str(first), "arguments": ["clang++", "-Icommon", "-Ifirst", "-c", str(first)]},
        {"directory": str(tmp_path), "file": str(second), "arguments": ["clang++", "-Icommon", "-Isecond", "-c", str(second)]},
    ]))
    graph = build_cxx_dep_graph(tmp_path)
    assert graph[str(shared)]["imports"] == {str(first_variant), str(second_variant)}
    assert graph[str(first_variant)]["importers"] == {str(shared)}
    assert graph[str(second_variant)]["importers"] == {str(shared)}


def test_relative_compile_directory_is_relative_to_database(tmp_path, monkeypatch):
    source = _write(tmp_path, "src/main.c", '#include "generated.h"\n')
    header = _write(tmp_path, "generated/generated.h", "#pragma once\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": "build",
                    "file": "../src/main.c",
                    "arguments": ["cc", "-I../generated", "-c", "../src/main.c"],
                }
            ]
        )
    )
    unrelated = tmp_path / "other"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    graph = build_cxx_dep_graph(tmp_path)

    assert str(header) in graph[str(source)]["imports"]
