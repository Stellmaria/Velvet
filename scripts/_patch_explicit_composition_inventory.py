from __future__ import annotations

from pathlib import Path
from textwrap import dedent


SCANNER = Path("scripts/inventory_package_architecture.py")
TEST = Path("tests/test_package_architecture_inventory.py")


INSTALLER_GRAPH = dedent(
    '''
    def _installer_graph(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_module = {str(row["module"]): row for row in modules}

        def graph_row(
            *,
            order: int,
            line: int,
            call: str,
            origin: str,
        ) -> dict[str, Any]:
            owner_module = origin.rsplit(".", 1)[0] if "." in origin else origin
            owner_row = by_module.get(owner_module, {})
            return {
                "order": order,
                "line": line,
                "call": call,
                "origin": origin,
                "owner_module": owner_module,
                "patched_symbols": list(
                    owner_row.get("foreign_assignment_targets", [])
                ),
            }

        composition = by_module.get("velvet_bot.app.composition")
        if composition is not None:
            path = ROOT / str(composition["path"])
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            aliases, _ = _imports(
                tree,
                "velvet_bot.app.composition",
                is_package=False,
            )
            functions = {
                node.name: node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            wrapper_origins: dict[str, str] = {}
            for name, function in functions.items():
                if not name.startswith("_install_"):
                    continue
                installer_calls = [
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call)
                    and _dotted(node.func).split(".")[-1].startswith("install_")
                ]
                if len(installer_calls) != 1:
                    continue
                local = _dotted(installer_calls[0].func)
                wrapper_origins[name] = aliases.get(local, local)

            def declared_stages(function_name: str) -> list[dict[str, Any]]:
                function = functions.get(function_name)
                if function is None:
                    return []
                stages: list[dict[str, Any]] = []
                for node in ast.walk(function):
                    if not isinstance(node, ast.Call):
                        continue
                    if _dotted(node.func).split(".")[-1] != "CompositionStage":
                        continue
                    if len(node.args) < 2:
                        continue
                    label = node.args[0]
                    if not isinstance(label, ast.Constant) or not isinstance(
                        label.value, str
                    ):
                        continue
                    installer = _dotted(node.args[1])
                    origin = wrapper_origins.get(
                        installer,
                        aliases.get(installer, installer),
                    )
                    stages.append(
                        {
                            "line": int(node.lineno),
                            "call": label.value,
                            "origin": origin,
                        }
                    )
                return sorted(stages, key=lambda row: int(row["line"]))

            declared = [
                *declared_stages("build_application_composition"),
                *declared_stages("_build_feature_stages"),
            ]
            if declared:
                return [
                    graph_row(
                        order=index,
                        line=int(item["line"]),
                        call=str(item["call"]),
                        origin=str(item["origin"]),
                    )
                    for index, item in enumerate(declared, start=1)
                ]

        app_init = by_module.get("velvet_bot.app")
        if app_init is None:
            return []
        path = ROOT / str(app_init["path"])
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases, _ = _imports(tree, "velvet_bot.app", is_package=True)
        graph: list[dict[str, Any]] = []
        for call in sorted(
            app_init["install_calls"],
            key=lambda row: int(row["line"]),
        ):
            local = str(call["call"]).split(".")[0]
            origin = aliases.get(local, local)
            graph.append(
                graph_row(
                    order=len(graph) + 1,
                    line=int(call["line"]),
                    call=str(call["call"]),
                    origin=origin,
                )
            )
        return graph
    '''
).lstrip()


def patch_scanner() -> None:
    source = SCANNER.read_text(encoding="utf-8")
    start = source.index("def _installer_graph(")
    end = source.index("\ndef _shared_fingerprint", start)
    SCANNER.write_text(
        source[:start] + INSTALLER_GRAPH + source[end:],
        encoding="utf-8",
    )


def patch_test() -> None:
    source = TEST.read_text(encoding="utf-8")
    replacements = {
        'self.assertEqual(604, self.inventory["production_module_count"])':
            'self.assertEqual(605, self.inventory["production_module_count"])',
        'self.assertEqual(128_870, self.inventory["production_loc"])':
            'self.assertEqual(129_015, self.inventory["production_loc"])',
        'self.assertEqual(518, self.inventory["violation_count"])':
            'self.assertEqual(516, self.inventory["violation_count"])',
        'Production modules: **604**': 'Production modules: **605**',
        'Registered package violations: **518**':
            'Registered package violations: **516**',
        'Registered exemptions: **518**':
            'Registered exemptions: **516**',
    }
    for old, new in replacements.items():
        if old not in source:
            raise RuntimeError(f"Expected package-test token is missing: {old}")
        source = source.replace(old, new)
    TEST.write_text(source, encoding="utf-8")


def main() -> None:
    patch_scanner()
    patch_test()
    compile(SCANNER.read_text(encoding="utf-8"), str(SCANNER), "exec")


if __name__ == "__main__":
    main()
