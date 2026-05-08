"""小程序监控包入口，导出监控控制器和分页常量。"""

from package.monitor.service import MiniProgramMonitor, PAGE_SIZE

__all__ = ["MiniProgramMonitor", "PAGE_SIZE"]
