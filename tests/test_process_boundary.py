import ast

import pytest

from conftest import REPO_ROOT, source_files

BACKEND = REPO_ROOT / "actions" / "backend.py"


def _imported_roots(path) -> set[str]:
    roots = set()

    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])

    return roots


def test_backend_does_not_import_the_frontend_process():
    # The backend runs in the plugin's own .venv, where StreamController and GTK do not exist
    roots = _imported_roots(BACKEND)
    assert "src" not in roots
    assert "gi" not in roots
    assert "globals" not in roots


@pytest.mark.parametrize(
    "path",
    [p for p in source_files() if p != BACKEND],
    ids=lambda p: p.name,
)
def test_frontend_does_not_import_pygame(path):
    # pygame lives only in the backend process; the frontend reaches it over rpyc
    assert "pygame" not in _imported_roots(path)
