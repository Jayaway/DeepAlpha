#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run DeepAlpha market-intelligence analysis against the LOCAL project.

This script is the callable entry point for the ``deepalpha-market-intel`` skill.
It imports the project's local adapter (``deepalpha_adapter.analyze_market_query``)
and prints a stable result, so the skill works directly inside a DeepAlpha
checkout without depending on any remote service.

Modes
-----
- ``history`` (default): analyze the local CSV history库 only. No browser,
  no cookies, no network. Fast and always runnable.
- ``crawl``: run the full realtime Selenium crawl path. Requires Chrome and a
  valid ``cookies/browser/x_cookie.json``. Enable with ``--crawl``.

Project root resolution order:
1. ``--project-root`` argument
2. ``DEEPALPHA_HOME`` environment variable
3. three levels up from this file (``<root>/skills/deepalpha-market-intel/scripts``)
"""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path


def _resolve_project_root(cli_root: str | None) -> Path:
    def has_adapter(path: Path) -> bool:
        return (path / "deepalpha_adapter.py").is_file()

    # An explicit --project-root must be valid; do not silently fall back.
    if cli_root:
        root = Path(cli_root)
        if not has_adapter(root):
            raise SystemExit(
                f"--project-root 无效：{root} 下找不到 deepalpha_adapter.py。"
            )
        return root.resolve()

    candidates = []
    env_root = os.getenv("DEEPALPHA_HOME")
    if env_root:
        candidates.append(Path(env_root))
    # <root>/skills/deepalpha-market-intel/scripts/deepalpha_analyze.py -> parents[3]
    candidates.append(Path(__file__).resolve().parents[3])

    for candidate in candidates:
        if has_adapter(candidate):
            return candidate.resolve()

    tried = "\n  ".join(str(c) for c in candidates)
    raise SystemExit(
        "无法定位 DeepAlpha 项目根目录（找不到 deepalpha_adapter.py）。\n"
        "请用 --project-root 指定，或设置环境变量 DEEPALPHA_HOME。\n"
        f"已尝试:\n  {tried}"
    )


@contextlib.contextmanager
def _stdout_to_stderr():
    """Redirect everything written to fd 1 (stdout) to fd 2 (stderr).

    The DeepAlpha pipeline prints progress chatter to stdout, which would
    corrupt ``--json`` output. Redirecting at the file-descriptor level also
    captures prints from the forked crawl worker, not just in-process prints.
    """
    sys.stdout.flush()
    saved_fd = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(saved_fd)


def _compact(data: dict) -> str:
    crawl = data.get("crawl") or {}
    stats = data.get("stats") or {}
    graph = data.get("graph") or {}
    node_count = graph.get("node_count")
    if node_count is None:
        node_count = len(graph.get("nodes") or []) if isinstance(graph, dict) else 0
    edge_count = graph.get("edge_count")
    if edge_count is None:
        edge_count = len(graph.get("edges") or []) if isinstance(graph, dict) else 0

    lines = [
        f"结论：{data.get('direction')} / 置信度 {data.get('confidence')}",
        f"资产：{data.get('asset')}",
        f"模式：{data.get('mode')} / 历史 {stats.get('total', 0)} 条 / 有效 {stats.get('relevant', 0)} 条 / 图谱 {node_count} 节点 {edge_count} 关系",
        f"摘要：{data.get('summary', '')}",
    ]
    errors = crawl.get("errors") or []
    if errors:
        lines.append(f"抓取错误：{len(errors)} 个（见 crawl.errors）")
    lines.append(f"风险提示：{data.get('disclaimer', '')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run DeepAlpha market intelligence analysis (local-first).",
    )
    parser.add_argument("query", help="行情问题，例如：今天油价会涨吗？")
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="执行实时抓取（需要 Chrome + cookies/browser/x_cookie.json）；默认只分析本地历史库。",
    )
    parser.add_argument(
        "--mode",
        choices=["history", "crawl"],
        default=None,
        help="显式指定模式，优先级高于 --crawl。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="实时抓取的超时秒数（仅 crawl 模式有意义；默认 420）。",
    )
    parser.add_argument("--json", action="store_true", help="输出完整结构化 JSON。")
    parser.add_argument(
        "--project-root",
        default=None,
        help="DeepAlpha 项目根目录（含 deepalpha_adapter.py）。",
    )
    args = parser.parse_args()

    root = _resolve_project_root(args.project_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Decide mode: explicit --mode wins, else --crawl flag, else history (safe default).
    if args.mode:
        mode = args.mode
    elif args.crawl:
        mode = "crawl"
    else:
        mode = "history"

    # History mode is synchronous and fast (timeout 0 = no subprocess guard).
    # Crawl mode keeps the adapter's subprocess timeout so a stuck browser
    # falls back to history instead of hanging forever.
    if args.timeout is not None:
        timeout_seconds = args.timeout
    elif mode == "history":
        timeout_seconds = 0
    else:
        timeout_seconds = 420

    try:
        from deepalpha_adapter import analyze_market_query
    except Exception as exc:  # noqa: BLE001 - surface import/setup failures clearly
        print(
            json.dumps(
                {"ok": False, "error": f"无法导入 deepalpha_adapter：{exc}", "query": args.query},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    try:
        with _stdout_to_stderr():
            data = analyze_market_query(args.query, mode=mode, timeout_seconds=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - analysis should still report structured failure
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "query": args.query, "mode": mode},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_compact(data))
    # A structured failure (mode=="error") is still printed, but the exit code
    # must be non-zero so callers and CI can detect it.
    return 1 if str(data.get("mode")) == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
