# -*- coding: utf-8 -*-
"""项目根目录与输出目录的唯一定位入口。

历史背景：仓库里曾有 9 处自实现的 `get_project_root` / `_find_project_root`
散落在不同 Skill 下，都在找不到 `data/` 时回落到 `os.getcwd()`。一旦 CWD
不可写（容器只读层、site-packages 等），后续 makedirs/to_csv 会直接 PermissionError。

本模块是唯一权威：
- `get_project_root()` —— 决定输入读自何处；遵循 RISK_PROJECT_ROOT > 显式入参 > 自动向上找 data/ > CWD 兜底。
- `get_output_root()` —— 决定结果写到何处；遵循 RISK_OUTPUT_ROOT > 复用 get_project_root()。
- `results_dir()` / `output_dir()` —— 拼好 `<output_root>/data/results[/<sub>]` 与 `<output_root>/output[/<sub>]`。
- `ensure_writable_dir(path)` —— makedirs；PermissionError 时改抛 RuntimeError，提示设置 RISK_OUTPUT_ROOT。

旧的 9 处函数保留为薄壳，内部 import 转发，向后兼容。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, os.PathLike]

ENV_PROJECT_ROOT = 'RISK_PROJECT_ROOT'
ENV_OUTPUT_ROOT = 'RISK_OUTPUT_ROOT'

# 内部缓存：避免每次调用都打印 [WARN] 兜底日志
_warned_no_data_dir: set = set()


def _walk_up_for_data(start: Path) -> Optional[Path]:
    """从 start 沿父链向上找首个含 data/ 的目录。"""
    for p in [start, *start.parents]:
        if (p / 'data').exists():
            return p
    return None


def get_project_root(start: Optional[PathLike] = None) -> str:
    """返回项目根目录的绝对路径。

    优先级：
        1. 环境变量 RISK_PROJECT_ROOT（直接采信，不验证 data/）
        2. start 参数（显式指定起点，从 start 向上找 data/）
        3. 自动从 CWD 向上找 data/
        4. CWD 兜底（带一次性 [WARN]）

    注意：刻意不再从 __file__ 位置兜底——那会找到 Skill 仓库本身的 data/，
    导致 chdir 到无关目录的脚本误把分析结果写回 Skill 源码树（正是我们要避免的）。
    """
    env_val = os.environ.get(ENV_PROJECT_ROOT)
    if env_val:
        return os.path.normpath(os.path.expandvars(os.path.expanduser(env_val)))

    if start is not None:
        start_path = Path(start).resolve()
        found = _walk_up_for_data(start_path)
        if found is not None:
            return str(found)

    cwd = Path(os.getcwd()).resolve()
    found = _walk_up_for_data(cwd)
    if found is not None:
        return str(found)

    cwd_str = str(cwd)
    if cwd_str not in _warned_no_data_dir:
        print(f'[WARN] 未找到 data/ 目录，使用当前工作目录作为项目根: {cwd_str}\n'
              f'       如需重定向，请设置环境变量 {ENV_PROJECT_ROOT}=<路径>')
        _warned_no_data_dir.add(cwd_str)
    return cwd_str


def get_output_root() -> str:
    """返回写盘根目录的绝对路径。

    优先级：
        1. 环境变量 RISK_OUTPUT_ROOT（直接采信）
        2. get_project_root()
    """
    env_val = os.environ.get(ENV_OUTPUT_ROOT)
    if env_val:
        return os.path.normpath(os.path.expandvars(os.path.expanduser(env_val)))
    return get_project_root()


def results_dir(subdir: Optional[str] = None) -> str:
    """`<output_root>/data/results[/<subdir>]`，不创建目录。"""
    base = os.path.join(get_output_root(), 'data', 'results')
    return os.path.join(base, subdir) if subdir else base


def output_dir(subdir: Optional[str] = None) -> str:
    """`<output_root>/output[/<subdir>]`，不创建目录。"""
    base = os.path.join(get_output_root(), 'output')
    return os.path.join(base, subdir) if subdir else base


# 推荐的统一产物目录布局（B10 引入；旧的 results_dir / output_dir 仍兼容）：
#   <output_root>/data/results/<project>/level1/    Level 1 产物（IV / LR / 规则）
#   <output_root>/data/results/<project>/level2/    Level 2 产物（trigger 三件套）
#   <output_root>/data/results/<project>/level3/    Level 3 产物（DOCX 报告 / LLM JSON）
# 新代码可调用 unified_results_dir 以避免「IV 在 data/results、trigger 在 output」的两处分裂。
_VALID_LEVELS = {'level1', 'level2', 'level3'}


def unified_results_dir(project: str, level: str = 'level1') -> str:
    """`<output_root>/data/results/<project>/<level>/`，不创建目录。

    level ∈ {'level1', 'level2', 'level3'}：
      - level1：IV / LR / 规则等分析产物（对齐 PipelineState 的 Level 1）
      - level2：trigger 客户级触碰三件套
      - level3：DOCX 报告 / 对外交付物
    """
    if level not in _VALID_LEVELS:
        raise ValueError(f"level 必须是 {sorted(_VALID_LEVELS)} 之一，实际：{level!r}")
    return os.path.join(get_output_root(), 'data', 'results', project, level)


def ensure_writable_dir(path: PathLike) -> str:
    """makedirs(exist_ok=True)；PermissionError 时改抛带提示的 RuntimeError。"""
    p = str(path)
    try:
        os.makedirs(p, exist_ok=True)
    except PermissionError as e:
        raise RuntimeError(
            f'无写权限：{p}\n'
            f'  原因：{e}\n'
            f'  解决：设置环境变量 {ENV_OUTPUT_ROOT}=<可写目录> 后重试，'
            f'例如 export {ENV_OUTPUT_ROOT}=$HOME/risk_out'
        ) from e
    return p
