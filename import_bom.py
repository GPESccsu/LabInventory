"""兼容入口：转发到 scripts.import_bom。"""
from scripts.import_bom import main


if __name__ == "__main__":
    raise SystemExit(main())
