"""从内置、entry point 与受控目录发现扩展。"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any

from .builtin import setup_builtin_extensions
from .registry import ExtensionRegistry, ExtensionSetup
from .trust import (
    ProjectTrustDecision,
    ProjectTrustStore,
    default_trust_store_path,
)

EXTENSION_ENTRY_POINT_GROUP = "dm_agent.extensions"
ProjectTrustPrompt = Callable[[Path], ProjectTrustDecision]


@dataclass(frozen=True)
class ExtensionLoadFailure:
    """单个扩展加载失败的可展示描述。"""

    source: str
    message: str


@dataclass
class ExtensionDiscoveryResult:
    """一次发现过程的注册表与诊断信息。"""

    registry: ExtensionRegistry
    loaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[ExtensionLoadFailure] = field(default_factory=list)


class ExtensionDiscoveryError(RuntimeError):
    """显式指定扩展无法加载时抛出。"""


def create_builtin_registry() -> ExtensionRegistry:
    """构造只含内置能力的注册表；不会发现或执行任何外部代码。"""
    registry = ExtensionRegistry()
    registry.apply_setup(setup_builtin_extensions, source="builtin")
    return registry


def discover_extensions(
    *,
    project_root: str | Path | None = None,
    home_dir: str | Path | None = None,
    no_extensions: bool = False,
    explicit_paths: Sequence[str | Path] = (),
    trust_prompt: ProjectTrustPrompt | None = None,
    trust_store_path: str | Path | None = None,
) -> ExtensionDiscoveryResult:
    """按 builtin < entry_points < 用户目录 < 项目目录 < 显式文件的顺序加载。"""
    project = (Path.cwd() if project_root is None else Path(project_root)).resolve()
    home = Path.home() if home_dir is None else Path(home_dir)
    registry = create_builtin_registry()
    result = ExtensionDiscoveryResult(registry=registry)
    result.loaded.append("builtin")

    if no_extensions:
        return result

    for entry_point in _extension_entry_points():
        source = f"entry_point:{_entry_point_label(entry_point)}"
        _load_entry_point(entry_point, source=source, result=result)

    _load_directory(
        home / ".dm_agent" / "extensions",
        source_prefix="user",
        result=result,
    )

    project_directory = project / ".dm_agent" / "extensions"
    project_files = _python_files(project_directory)
    if project_files:
        store = ProjectTrustStore(trust_store_path or default_trust_store_path(home))
        decision = store.get(project)
        should_load = decision is True
        if decision is False:
            result.skipped.append(f"project:{project} (已持久拒绝)")
        elif decision is None:
            prompt_decision = (
                trust_prompt(project)
                if trust_prompt is not None
                else ProjectTrustDecision.SKIP_ONCE
            )
            should_load = prompt_decision in {
                ProjectTrustDecision.LOAD_ONCE,
                ProjectTrustDecision.TRUST,
            }
            if prompt_decision is ProjectTrustDecision.TRUST:
                _persist_trust(store, project, trusted=True, result=result)
            elif prompt_decision is ProjectTrustDecision.DENY:
                _persist_trust(store, project, trusted=False, result=result)
            if not should_load:
                result.skipped.append(f"project:{project} (未获信任)")
        if should_load:
            _load_files(project_files, source_prefix="project", result=result)

    for path_value in explicit_paths:
        path = Path(path_value).expanduser().resolve()
        source = f"explicit:{path}"
        try:
            _load_file(path, source=source, registry=registry)
        except Exception as exc:
            raise ExtensionDiscoveryError(
                f"显式扩展加载失败 {path}: {type(exc).__name__}: {exc}"
            ) from exc
        result.loaded.append(source)

    return result


def _extension_entry_points() -> list[Any]:
    discovered: Iterable[Any]
    try:
        discovered = metadata.entry_points(group=EXTENSION_ENTRY_POINT_GROUP)
    except TypeError:
        all_entry_points = metadata.entry_points()
        if hasattr(all_entry_points, "select"):
            discovered = all_entry_points.select(group=EXTENSION_ENTRY_POINT_GROUP)
        else:
            legacy_get = getattr(all_entry_points, "get", None)
            discovered = legacy_get(EXTENSION_ENTRY_POINT_GROUP, ()) if callable(legacy_get) else ()
    return sorted(discovered, key=_entry_point_sort_key)


def _entry_point_sort_key(entry_point: Any) -> tuple[str, str, str]:
    distribution = getattr(getattr(entry_point, "dist", None), "name", "")
    return (
        str(getattr(entry_point, "name", "")),
        str(getattr(entry_point, "value", "")),
        str(distribution),
    )


def _entry_point_label(entry_point: Any) -> str:
    name = str(getattr(entry_point, "name", "")) or "unnamed"
    value = str(getattr(entry_point, "value", ""))
    return f"{name}={value}" if value else name


def _load_entry_point(
    entry_point: Any,
    *,
    source: str,
    result: ExtensionDiscoveryResult,
) -> None:
    try:
        loaded = entry_point.load()
        setup = _resolve_setup(loaded)
        result.registry.apply_setup(setup, source=source)
    except Exception as exc:
        result.failures.append(ExtensionLoadFailure(source, f"{type(exc).__name__}: {exc}"))
        return
    result.loaded.append(source)


def _load_directory(
    directory: Path,
    *,
    source_prefix: str,
    result: ExtensionDiscoveryResult,
) -> None:
    _load_files(_python_files(directory), source_prefix=source_prefix, result=result)


def _load_files(
    paths: Iterable[Path],
    *,
    source_prefix: str,
    result: ExtensionDiscoveryResult,
) -> None:
    for path in paths:
        source = f"{source_prefix}:{path.resolve()}"
        try:
            _load_file(path, source=source, registry=result.registry)
        except Exception as exc:
            result.failures.append(ExtensionLoadFailure(source, f"{type(exc).__name__}: {exc}"))
            continue
        result.loaded.append(source)


def _python_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.glob("*.py") if path.is_file()),
        key=lambda path: (path.name.casefold(), path.name),
    )


def _load_file(path: Path, *, source: str, registry: ExtensionRegistry) -> None:
    if path.suffix.casefold() != ".py" or not path.is_file():
        raise ValueError("扩展路径必须是存在的 .py 文件")
    module = _import_module_from_path(path)
    registry.apply_setup(_resolve_setup(module), source=source)


def _import_module_from_path(path: Path) -> ModuleType:
    resolved = path.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    module_name = f"_dm_agent_extension_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为扩展创建模块规范: {resolved}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module


def _resolve_setup(loaded: Any) -> ExtensionSetup:
    setup: Any = loaded if callable(loaded) else getattr(loaded, "setup", None)
    if not callable(setup):
        raise TypeError("扩展必须导出可调用的 setup(api) 函数")
    return setup


def _persist_trust(
    store: ProjectTrustStore,
    project: Path,
    *,
    trusted: bool,
    result: ExtensionDiscoveryResult,
) -> None:
    try:
        store.set(project, trusted=trusted)
    except OSError as exc:
        result.failures.append(
            ExtensionLoadFailure(
                f"trust:{project}",
                f"信任决定保存失败，将只对本次进程生效: {exc}",
            )
        )
