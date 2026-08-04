"""Windows 垫片：swebench harness 只用 resource 抬高文件描述符上限。

harness 在 prepare_images.py / run_evaluation.py 里调用
``resource.setrlimit(resource.RLIMIT_NOFILE, ...)``，纯粹是为了让高并发 docker
调用不撞上 ulimit。Windows 没有这个模块，也没有对应的限制，于是这里提供一组
no-op：语义上等价于"上限足够高，无需调整"。

放在独立目录经 PYTHONPATH 注入，不污染 venv 的 site-packages。
"""

from __future__ import annotations

RLIMIT_NOFILE = 7
RLIMIT_CORE = 4
RLIM_INFINITY = -1


def getrlimit(resource_id: int) -> tuple[int, int]:
    # Windows 上 CRT 的默认上限已远高于 harness 会用到的并发量。
    return (8192, 8192)


def setrlimit(resource_id: int, limits: tuple[int, int]) -> None:
    return None
