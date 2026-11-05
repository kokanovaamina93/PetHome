
import ast
from pathlib import Path


def test_backend_main_exists():
    """Проверяем наличие основного файла backend."""
    path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
    assert path.is_file(), "Файл backend/main.py не найден"


def test_backend_python_syntax():
    """Проверяем синтаксис основного Python-файла."""
    path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)

