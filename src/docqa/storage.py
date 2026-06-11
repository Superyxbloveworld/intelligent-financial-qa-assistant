from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import TypeVar

from .models import FinancialCell, PageDiagnostic, to_dict

T = TypeVar("T", FinancialCell, PageDiagnostic)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, values: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(to_dict(value), ensure_ascii=False) for value in values) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path, cls: type[T]) -> list[T]:
    names = {field.name for field in fields(cls)}
    return [
        cls(**{key: value for key, value in json.loads(line).items() if key in names})
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
