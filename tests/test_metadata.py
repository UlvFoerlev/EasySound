import ast

import pytest


def _register_kwargs(main_ast: ast.Module) -> dict:
    for node in ast.walk(main_ast):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register"
        ):
            return {kw.arg: kw.value for kw in node.keywords}
    pytest.fail("no self.register(...) call found in main.py")


def test_manifest_and_plugin_version_agree(manifest, main_ast):
    # CLAUDE.md requires manifest.json version and main.py plugin_version to stay in sync
    plugin_version = _register_kwargs(main_ast)["plugin_version"]
    assert isinstance(plugin_version, ast.Constant)
    assert manifest["version"] == plugin_version.value


def test_versions_are_dotted_numeric(manifest):
    assert manifest["version"].count(".") == 2
    assert all(part.isdigit() for part in manifest["version"].split("."))


def test_register_declares_an_app_version(main_ast):
    app_version = _register_kwargs(main_ast).get("app_version")
    assert isinstance(app_version, ast.Constant)
    assert app_version.value


def test_manifest_identity_fields(manifest):
    assert manifest["id"] == "uf_easy_sound"
    assert manifest["name"]
    assert manifest["descriptions"]["en_US"]
