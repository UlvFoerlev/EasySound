import ast

import pytest

LEGACY_ID = "dev_core477_EasySound::PlaySound"


def _action_holder_calls(main_ast: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ActionHolder"
    ]


def _kwargs(call: ast.Call) -> dict:
    return {kw.arg: kw.value for kw in call.keywords}


@pytest.fixture(scope="module")
def holder_calls(main_ast):
    calls = _action_holder_calls(main_ast)
    assert calls, "no ActionHolder(...) calls found in main.py"
    return calls


def test_legacy_action_id_constant_is_unchanged(main_ast):
    # Existing user pages resolve this id by exact match; changing it orphans every pre-v2 button
    values = [
        node.value.value
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and any(
            isinstance(t, ast.Name) and t.id == "LEGACY_PLAY_SOUND_ACTION_ID"
            for t in node.targets
        )
    ]
    assert values == [LEGACY_ID]


def test_both_the_canonical_and_legacy_holders_are_registered(holder_calls):
    suffixes, legacy = [], []

    for call in holder_calls:
        kwargs = _kwargs(call)
        if "action_id_suffix" in kwargs:
            suffixes.append(kwargs["action_id_suffix"].value)
        action_id = kwargs.get("action_id")
        if isinstance(action_id, ast.Name):
            legacy.append(action_id.id)

    assert suffixes == ["PlaySound"]
    assert legacy == ["LEGACY_PLAY_SOUND_ACTION_ID"]


def test_holders_use_action_core_not_the_deprecated_action_base(holder_calls):
    for call in holder_calls:
        kwargs = _kwargs(call)
        assert "action_core" in kwargs
        assert "action_base" not in kwargs


def test_key_input_is_declared_supported(holder_calls):
    for call in holder_calls:
        support = _kwargs(call)["action_support"]
        # Omitting action_support defaults every input to UNTESTED, which warns users on a working action
        assert isinstance(support, ast.Name)
        assert support.id == "action_support"
