import ast

import pytest

from conftest import call_kwargs, calls_named


def _register_kwargs(main_ast: ast.Module) -> dict:
    calls = calls_named(main_ast, "register")
    if not calls:
        pytest.fail("no self.register(...) call found in main.py")

    return call_kwargs(calls[0])


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


def test_manifest_declares_the_store_fields(manifest):
    # The plugin template documents these, and the store carries them into its listing
    assert manifest["github"] == "https://github.com/UlvFoerlev/EasySound"
    assert manifest["app-version"]
    assert manifest["minimum-app-version"]


def test_manifest_app_version_matches_register(manifest, main_ast):
    """The floor StreamController enforces comes from register(); the manifest must not contradict it."""
    declared = _register_kwargs(main_ast)["app_version"]

    assert isinstance(declared, ast.Constant)
    assert manifest["app-version"] == declared.value
    assert manifest["minimum-app-version"] == declared.value


def test_about_json_names_both_copyright_holders(repo_root):
    import json

    about = json.loads((repo_root / "about.json").read_text())

    assert about["author"]
    assert "Core447" in about["copyright"]
    assert "UlvFoerlev" in about["copyright"]
    assert about["support"].startswith("https://")
