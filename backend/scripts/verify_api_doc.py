"""接口文档与代码路由一致性校验。

用法（在 backend/ 目录）：
    python scripts/verify_api_doc.py

解析 docs/API.md 中的接口清单表格（形如 | GET | `/tasks` | ...），
与 FastAPI 应用的实际路由比对（路径参数名归一化，如 {id} == {session_id}）。
不一致时退出码非 0。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "API.md"
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PARAM_RE = re.compile(r"\{[^}]*\}")
ROW_RE = re.compile(r"^\|\s*([A-Z/]+)\s*\|\s*`([^`]+)`")


def normalize_path(path: str) -> str:
    return PARAM_RE.sub("{}", path.rstrip("/"))


def doc_endpoints() -> set[tuple[str, str]]:
    text = DOC_PATH.read_text(encoding="utf-8")
    found: set[tuple[str, str]] = set()
    for line in text.splitlines():
        match = ROW_RE.match(line.strip())
        if not match:
            continue
        methods_raw, path = match.group(1), match.group(2)
        if not path.startswith("/"):
            continue
        for method in methods_raw.split("/"):
            method = method.strip()
            if method in METHODS:
                found.add((method, normalize_path(path)))
    return found


def code_endpoints() -> set[tuple[str, str]]:
    prefix = get_settings().api_prefix
    schema = app.openapi()
    found: set[tuple[str, str]] = set()
    for path, ops in schema["paths"].items():
        relative = path[len(prefix):] if path.startswith(prefix) else path
        for method in ops:
            found.add((method.upper(), normalize_path(relative)))
    return found


def main() -> int:
    doc = doc_endpoints()
    code = code_endpoints()
    missing_in_doc = sorted(code - doc)
    extra_in_doc = sorted(doc - code)

    print(f"文档接口：{len(doc)} 个   代码路由：{len(code)} 个")
    if not missing_in_doc and not extra_in_doc:
        print("一致性校验通过：文档与代码完全一致。")
        return 0
    if missing_in_doc:
        print(f"\n代码有、文档未覆盖（{len(missing_in_doc)}）：")
        for method, path in missing_in_doc:
            print(f"  - {method} {path}")
    if extra_in_doc:
        print(f"\n文档有、代码未实现（{len(extra_in_doc)}）：")
        for method, path in extra_in_doc:
            print(f"  - {method} {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
