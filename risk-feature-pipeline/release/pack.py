#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 release/manifest.yaml 清单打包 risk-feature-pipeline 技能发布包。

示例：
  python release/pack.py
  python release/pack.py --profile agent-core --out /tmp/risk-skill
  python release/pack.py --archive              # 额外生成 .zip（默认）
  python release/pack.py --archive --archive-format tar.gz
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.yaml"


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit(
            "打包需要 PyYAML：pip install pyyaml\n"
            "（仅打包脚本依赖，发布包本体已在 pyproject.toml 声明 pyyaml）"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _read_version(manifest: dict) -> str:
    src = manifest.get("skill", {}).get("version_source", "pyproject.toml")
    if src != "pyproject.toml":
        return manifest.get("skill", {}).get("version", "0.0.0")
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        raise SystemExit("无法从 pyproject.toml 解析 version")
    return m.group(1)


def _resolve_profile(manifest: dict, name: str) -> dict:
    profiles = manifest["profiles"]
    if name not in profiles:
        raise SystemExit(f"未知 profile: {name!r}，可选: {', '.join(profiles)}")
    prof = dict(profiles[name])
    extends = prof.pop("extends", None)
    if extends:
        base = _resolve_profile(manifest, extends)
        merged = {**base, **prof}
        merged["extra_include"] = _merge_include(
            base.get("extra_include"),
            prof.get("extra_include"),
        )
        return merged
    return prof


def _merge_include(a: dict | None, b: dict | None) -> dict:
    out: dict = {"files": [], "globs": []}
    for src in (a, b):
        if not src:
            continue
        out["files"].extend(src.get("files", []))
        out["globs"].extend(src.get("globs", []))
    return out


def _norm_rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _match_glob(rel: str, pattern: str) -> bool:
    # Path.glob 语义：** 匹配任意层级
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    return fnmatch.fnmatch(rel, pattern)


def _collect_candidates(manifest: dict, profile: dict) -> list[Path]:
    include = manifest["include"]
    extra = profile.get("extra_include") or {}

    extra_files = list(extra.get("files", []))
    extra_globs = list(extra.get("globs", []))

    files = list(include.get("files", []))
    files.extend(extra_files)

    globs = list(include.get("globs", []))
    globs.extend(extra_globs)

    exclude = manifest["exclude"]
    ex_globs = exclude.get("globs", [])
    ex_dirs = set(exclude.get("dirs", []))
    ex_files = set(exclude.get("files", []))
    allow_lock = set(manifest.get("allow_lock_files", []))

    seen: set[str] = set()
    out: list[Path] = []
    force_include: set[str] = set()

    def add(path: Path):
        rel = _norm_rel(path)
        if rel in seen or not path.is_file():
            return
        seen.add(rel)
        out.append(path)

    def iter_pattern(pattern: str):
        if "**" in pattern:
            prefix = pattern.split("**", 1)[0].rstrip("/")
            root = REPO_ROOT / prefix if prefix else REPO_ROOT
            if not root.exists():
                return
            for p in root.rglob("*"):
                if p.is_file():
                    rel = _norm_rel(p)
                    if _match_glob(rel, pattern):
                        yield p
        else:
            for p in REPO_ROOT.glob(pattern):
                if p.is_file():
                    yield p

    for f in files:
        p = REPO_ROOT / f
        if p.is_file():
            add(p)

    for f in extra_files:
        p = REPO_ROOT / f
        if p.is_file():
            force_include.add(_norm_rel(p))

    for pattern in extra_globs:
        for p in iter_pattern(pattern):
            force_include.add(_norm_rel(p))

    for pattern in globs:
        for p in iter_pattern(pattern):
            add(p)

    filtered: list[Path] = []
    skip_dir_names = set(ex_dirs) | {"node_modules", "__pycache__", ".pytest_cache", ".git", ".claude"}
    for p in sorted(out, key=lambda x: _norm_rel(x)):
        rel = _norm_rel(p)
        parts = rel.split("/")

        if rel in force_include:
            filtered.append(p)
            continue
        if any(part in skip_dir_names for part in parts):
            continue
        if rel in ex_files:
            continue
        if rel in allow_lock:
            filtered.append(p)
            continue
        if rel.endswith(".lock"):
            continue
        if any(_match_glob(rel, g) for g in ex_globs):
            continue
        filtered.append(p)

    return filtered


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_install_txt(dest: Path, manifest: dict, profile: dict, version: str):
    tpl = manifest.get("post_install_template", {})
    lines = [
        f"# risk-feature-pipeline v{version} 安装说明",
        f"# profile: {profile.get('description', '').strip()}",
        "",
        "## 1. Python 依赖",
    ]
    for step in tpl.get("shared", []):
        lines.append(step)
    for extra in profile.get("pip_extras", []):
        for step in tpl.get("per_extra", {}).get(extra, []):
            lines.append(step)

    node_steps = profile.get("node_install") or []
    if node_steps:
        lines.extend(["", "## 2. Node 依赖（report 子命令需要）"])
        for item in node_steps:
            d = item["directory"]
            cmd = item["command"]
            lines.append(f"cd <SKILL_ROOT>/{d} && {cmd}")

    lines.extend([
        "",
        "## 3. 沙盒 / agent 环境变量（每次会话启动前设置）",
        "export RISK_PROJECT_ROOT=<用户数据工作区>",
        "export RISK_OUTPUT_ROOT=<可写输出工作区>",
        "",
        "## 4. 验证",
    ])
    for cmd in manifest.get("runtime", {}).get("verify_after_install", []):
        lines.append(cmd)

    (dest / "INSTALL.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_archive(
    out_dir: Path,
    archive_path: Path,
    archive_format: str,
    arc_root: str,
) -> None:
    if archive_format == "zip":
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(out_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(out_dir).as_posix()
                zf.write(file_path, f"{arc_root}/{rel}")
        return
    if archive_format == "tar.gz":
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(out_dir, arcname=arc_root)
        return
    raise SystemExit(f"不支持的归档格式: {archive_format!r}，可选: zip, tar.gz")


def pack(
    profile_name: str,
    out_dir: Path,
    make_archive: bool,
    archive_format: str = "zip",
) -> dict:
    manifest = _load_yaml(MANIFEST_PATH)
    profile = _resolve_profile(manifest, profile_name)
    version = _read_version(manifest)
    skill_name = manifest["skill"]["name"]

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    files = _collect_candidates(manifest, profile)
    if not files:
        raise SystemExit("清单匹配到 0 个文件，请检查 manifest.yaml")

    file_records = []
    for src in files:
        rel = _norm_rel(src)
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        file_records.append({
            "path": rel,
            "bytes": src.stat().st_size,
            "sha256": _sha256(src),
        })

    _write_install_txt(out_dir, manifest, profile, version)

    lock = {
        "schema_version": manifest["schema_version"],
        "skill": skill_name,
        "version": version,
        "profile": profile_name,
        "packed_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(REPO_ROOT),
        "file_count": len(file_records),
        "total_bytes": sum(r["bytes"] for r in file_records),
        "files": file_records,
        "runtime": manifest.get("runtime", {}),
        "pip_extras": profile.get("pip_extras", []),
        "node_install": profile.get("node_install", []),
    }
    lock_path = out_dir / "release.lock.json"
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive_path = None
    if make_archive:
        suffix = ".zip" if archive_format == "zip" else ".tar.gz"
        archive_path = out_dir.parent / f"{skill_name}-{version}-{profile_name}{suffix}"
        arc_root = f"{skill_name}-{version}"
        _write_archive(out_dir, archive_path, archive_format, arc_root)
        lock["archive"] = str(archive_path)
        lock["archive_format"] = archive_format

    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按 manifest.yaml 打包技能发布包")
    parser.add_argument(
        "--profile",
        default="agent-runtime",
        help="manifest.yaml profiles 下的配置名（默认 agent-runtime）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "dist" / "risk-feature-pipeline",
        help="输出目录（默认 dist/risk-feature-pipeline）",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="在输出目录旁额外生成归档（默认 .zip）",
    )
    parser.add_argument(
        "--archive-format",
        choices=("zip", "tar.gz"),
        default="zip",
        help="--archive 时使用的格式（默认 zip，沙盒/agent 部署常用）",
    )
    args = parser.parse_args(argv)

    lock = pack(
        args.profile,
        args.out.resolve(),
        args.archive,
        archive_format=args.archive_format,
    )
    print(f"[pack] OK | skill={lock['skill']} | version={lock['version']} | "
          f"profile={lock['profile']} | files={lock['file_count']} | "
          f"bytes={lock['total_bytes']}")
    print(f"outputs: {args.out.resolve()}")
    print(f"         {args.out.resolve() / 'release.lock.json'}")
    print(f"         {args.out.resolve() / 'INSTALL.txt'}")
    if args.archive:
        print(f"         {lock.get('archive')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
