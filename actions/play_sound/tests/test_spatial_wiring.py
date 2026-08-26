import ast

import pytest

from conftest import REPO_ROOT

SOURCE = REPO_ROOT / "actions" / "play_sound" / "play_sound.py"


@pytest.fixture(scope="module")
def action() -> ast.ClassDef:
    tree = ast.parse(SOURCE.read_text())
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PlaySoundAction"
    ]
    assert classes, "PlaySoundAction not found"

    return classes[0]


def method(action: ast.ClassDef, name: str) -> ast.FunctionDef:
    found = [
        node
        for node in action.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert found, f"PlaySoundAction.{name} is missing"

    return found[0]


def called_names(node: ast.AST) -> set[str]:
    return {
        getattr(call.func, "id", None) or getattr(call.func, "attr", None)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def test_delays_use_the_same_layout_as_the_gains(action):
    """Placing an unplaced speaker on the listener gives it no flight time, so it never gets a delay."""
    assert "emitter_layout" in called_names(method(action, "spatial_delays"))
