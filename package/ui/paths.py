"""解析应用配置文件、数据库和反编译输出目录路径。"""

from pathlib import Path

from PySide6.QtCore import QStandardPaths


def project_root() -> Path:
    """????????"""
    return Path(__file__).resolve().parents[2]


def app_config_dir() -> Path:
    """?? Qt ???????"""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if base:
        return Path(base)
    return project_root() / ".config"


def config_path() -> Path:
    """???????????"""
    return app_config_dir() / "state.json"


def wxid_db_path() -> Path:
    """?????????????"""
    return project_root() / "wxid.db"


def output_root_path() -> Path:
    """???????????"""
    return project_root() / "output"
