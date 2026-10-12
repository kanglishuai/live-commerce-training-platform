"""初始化数据库：建表 + 演示数据（幂等）。

用法（在 backend/ 目录下运行）：
    python scripts/init_db.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.base import get_session_factory, init_db  # noqa: E402
from app.db.seed import seed_demo_data  # noqa: E402


def main() -> None:
    settings = get_settings()
    safe_url = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"数据库：{safe_url}")
    print("创建表结构（幂等）...")
    init_db()
    print("写入演示数据（幂等）...")
    db = get_session_factory()()
    try:
        result = seed_demo_data(db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()
    print("完成。")


if __name__ == "__main__":
    main()
