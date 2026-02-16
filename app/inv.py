"""兼容入口：转发到 backend.app.inv。"""
from backend.app.inv import *  # noqa: F401,F403
from backend.app.inv import main

if __name__ == "__main__":
    main()
