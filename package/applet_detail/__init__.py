"""小程序详情页包入口，按需导出详情页主窗口和页面组件。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from package.applet_detail.widgets import AppletDetailPage, AppletDetailWindow

__all__ = ["AppletDetailPage", "AppletDetailWindow"]


def __getattr__(name: str):
    """延迟加载重量级 UI 组件，避免功能页之间形成循环导入。"""
    if name == "AppletDetailPage":
        from package.applet_detail.widgets import AppletDetailPage

        return AppletDetailPage
    if name == "AppletDetailWindow":
        from package.applet_detail.widgets import AppletDetailWindow

        return AppletDetailWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
