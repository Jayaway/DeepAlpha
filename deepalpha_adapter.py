#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web adapter for the local DeepAlpha analysis pipeline.

The public contract is intentionally small:

    analyze_market_query("今天油价会涨吗？") -> dict

It attempts the full realtime crawl path by default, then returns a stable
JSON shape that the public FastAPI service and web UI can consume.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import traceback
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from types import SimpleNamespace
from typing import Any


DISCLAIMER = "本系统输出仅用于信息分析与项目演示，不构成任何投资建议。"
PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass
class AnalyzeOptions:
    mode: str = "crawl"
    timeout_seconds: int = 420
    cookie_file: str = "cookies/browser/x_cookie.json"
    browser: str = "chrome"
    headless: bool = True
    delay: int = 1
    accounts_per_round: int = 5
    tweets_per_account: int = 20
    search_tasks_per_round: int = 2
    tweets_per_search: int = 30
    new_cleaner: bool = True
    debug: bool = False


def analyze_market_query(query: str, mode: str | None = None, timeout_seconds: int | None = None) -> dict[str, Any]:
    """Analyze a market query and return a stable API response.

    By default this uses a separate process so Selenium/browser hangs do not
    pin the web worker forever. Set ``DEEPALPHA_ANALYZE_MODE=history`` for a
    no-browser history-only fallback in constrained environments.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return _failure_response("", "query 不能为空")

    options = _options_from_env(mode=mode, timeout_seconds=timeout_seconds)
    # The pipeline chdir's into the project root (relative paths like
    # ./抓取的信息/ depend on it). Restore the caller's cwd afterwards so using
    # this adapter as a library does not silently move the host process.
    original_cwd = os.getcwd()
    try:
        return _run_with_timeout(clean_query, options)
    finally:
        try:
            os.chdir(original_cwd)
        except OSError:
            pass


def _run_with_timeout(query: str, options: AnalyzeOptions) -> dict[str, Any]:
    if options.timeout_seconds <= 0:
        return _analyze_market_query_sync(query, options)

    ctx = _multiprocessing_context()
    queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_worker, args=(query, options, queue), daemon=True)
    process.start()
    process.join(options.timeout_seconds)

    if process.is_alive():
        _terminate_process_tree(process)
        process.join(5)
        return _history_fallback_response(
            query,
            error=f"实时分析超过 {options.timeout_seconds} 秒，已终止本次抓取。",
            mode="timeout_fallback",
        )

    try:
        status, payload = queue.get(timeout=2)
    except Empty:
        if process.exitcode == 0:
            return _failure_response(query, "分析进程结束但没有返回结果")
        return _history_fallback_response(query, error=f"分析进程异常退出：exitcode={process.exitcode}", mode="process_fallback")

    if status == "ok":
        return payload
    return _history_fallback_response(query, error=str(payload), mode="error_fallback")


def _worker(query: str, options: AnalyzeOptions, queue) -> None:
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            pass
    try:
        queue.put(("ok", _analyze_market_query_sync(query, options)))
    except BaseException as exc:  # keep the public API structured even on hard failures
        if options.debug:
            traceback.print_exc()
        queue.put(("error", str(exc)))


def _analyze_market_query_sync(query: str, options: AnalyzeOptions) -> dict[str, Any]:
    _enter_project_root()
    from deepalpha.run_v2 import _configure_logging, _make_decision

    _configure_logging(options.debug)
    args = _runtime_args(options)
    decision = _make_decision(query, args, ai=None)
    _apply_web_crawl_budget(decision, options)

    if options.mode == "history":
        return _history_response(query, decision, mode="history")

    return _crawl_response(query, decision, args)


def _crawl_response(query: str, decision: dict[str, Any], args: SimpleNamespace) -> dict[str, Any]:
    from deepalpha.crawler_runner import run_all_tasks, save_results
    from deepalpha.run_v2 import _clean_tweets, _filter_tweets_for_query, _generate_graph, _judge_signals

    crawl_results = run_all_tasks(
        decision,
        cookie_file=args.cookie_file,
        browser=args.browser,
        headless="yes" if args.headless else "no",
        delay_between_tasks=args.delay,
        debug=args.debug,
    )

    all_tweets = crawl_results.get("all_tweets") or []
    csv_path = save_results(crawl_results) if all_tweets else None
    graph_result = _generate_graph(args, query, all_tweets) if not args.no_graph and all_tweets else None

    if not all_tweets:
        return _history_response(
            query,
            decision,
            mode="crawl_empty_fallback",
            crawl_results=crawl_results,
            prefix="实时抓取未返回有效情报，已回退历史库分析。",
        )

    relevant_tweets = _filter_tweets_for_query(all_tweets, query, decision)
    cleaned_tweets = _clean_tweets(relevant_tweets, args, ai=None)
    judgment = _judge_signals(cleaned_tweets, decision, args) or _empty_judgment()

    return _format_response(
        query=query,
        mode="crawl",
        decision=decision,
        judgment=judgment,
        total_tweets=len(all_tweets),
        relevant_count=len(cleaned_tweets),
        top_tweets=cleaned_tweets[:8],
        crawl_results=crawl_results,
        graph_result=graph_result,
        csv_path=csv_path,
        summary_prefix=None,
    )


def _history_response(
    query: str,
    decision: dict[str, Any],
    mode: str,
    crawl_results: dict[str, Any] | None = None,
    prefix: str | None = None,
) -> dict[str, Any]:
    from deepalpha.graph_engine import generate_graph_data
    from deepalpha.intel_analyzer import analyze_history

    analysis = analyze_history(query, decision)
    try:
        graph_result = generate_graph_data(input_dir="./抓取的信息/", output_file="./graph_data/关系图谱.json", query=query)
    except Exception:
        graph_result = None

    return _format_response(
        query=query,
        mode=mode,
        decision=decision,
        judgment=analysis.get("judgment") or _empty_judgment(),
        total_tweets=analysis.get("total_tweets", 0),
        relevant_count=analysis.get("relevant_count", 0),
        top_tweets=analysis.get("top_tweets") or [],
        crawl_results=crawl_results,
        graph_result=graph_result,
        csv_path=None,
        summary_prefix=prefix,
        summary_lines=analysis.get("summary_lines") or [],
    )


def _history_fallback_response(query: str, error: str, mode: str) -> dict[str, Any]:
    _enter_project_root()
    try:
        from deepalpha.intel_router_v2 import decide

        decision = decide(query).to_dict()
        return _history_response(query, decision, mode=mode, prefix=f"{error} 已回退历史库分析。")
    except Exception as exc:
        return _failure_response(query, f"{error}；历史库回退也失败：{exc}")


def _format_response(
    *,
    query: str,
    mode: str,
    decision: dict[str, Any],
    judgment: dict[str, Any],
    total_tweets: int,
    relevant_count: int,
    top_tweets: list[dict[str, Any]],
    crawl_results: dict[str, Any] | None,
    graph_result: dict[str, Any] | None,
    csv_path: str | None,
    summary_prefix: str | None,
    summary_lines: list[str] | None = None,
) -> dict[str, Any]:
    direction = _direction_code(judgment.get("market_direction"))
    confidence = float(judgment.get("aggregate_confidence") or 0)
    signals = _signals_from_judgment(judgment)
    errors = (crawl_results or {}).get("errors") or []
    summary = _build_summary(
        mode=mode,
        prefix=summary_prefix,
        asset=decision.get("asset", "unknown"),
        direction_label=judgment.get("market_direction_label") or "无明确方向",
        confidence=confidence,
        total_tweets=total_tweets,
        relevant_count=relevant_count,
        errors=errors,
        summary_lines=summary_lines or [],
    )

    response = {
        "query": query,
        "asset": decision.get("asset", "unknown"),
        "direction": direction,
        "confidence": confidence,
        "summary": summary,
        "signals": signals,
        "disclaimer": DISCLAIMER,
        "mode": mode,
        "decision": decision,
        "crawl": {
            "total": len((crawl_results or {}).get("all_tweets") or []),
            "errors": errors,
            "csv_path": csv_path,
        },
        "stats": {
            "total": total_tweets,
            "relevant": relevant_count,
            # generate_graph_data() returns counts, not the node/edge arrays
            # (those go to the graph JSON file). Prefer the counts; fall back to
            # array lengths only if a future path returns inline nodes/edges.
            "graph_nodes": (graph_result or {}).get("node_count", len((graph_result or {}).get("nodes") or [])),
            "graph_edges": (graph_result or {}).get("edge_count", len((graph_result or {}).get("edges") or [])),
        },
        "plan": {
            "core_variable": f"{query} / asset={decision.get('asset', 'unknown')}",
            "time_window": "实时抓取优先；失败时回退本地历史情报库。",
            "sources": [str(item).lstrip("@") for item in decision.get("top_accounts", [])],
            "signals": _ui_signal_chips(decision, relevant_count, errors),
        },
        "report": {
            "title": f"{query}：DeepAlpha 实时情报分析",
            "lead": summary,
            "summary_lines": summary_lines or [summary],
            "rows": _ui_rows(decision, judgment, total_tweets, relevant_count, errors),
            "events": _events_from_judgment(judgment) or _events_from_tweets(top_tweets),
            "direction": judgment.get("market_direction_label") or "无明确方向",
            "evidence": _evidence_text(judgment, relevant_count, confidence),
            "risk": DISCLAIMER,
            "top_tweets": top_tweets[:5],
        },
        "graph": graph_result,
    }
    if decision.get("asset") == "oil":
        response["ai_context"] = _ai_context_for_oil(
            query=query,
            mode=mode,
            decision=decision,
            judgment=judgment,
            top_tweets=top_tweets,
            errors=errors,
        )
    return response


def _build_summary(
    *,
    mode: str,
    prefix: str | None,
    asset: str,
    direction_label: str,
    confidence: float,
    total_tweets: int,
    relevant_count: int,
    errors: list[Any],
    summary_lines: list[str],
) -> str:
    parts = []
    if prefix:
        parts.append(prefix)
    if summary_lines:
        parts.extend(str(line).lstrip("- ").strip() for line in summary_lines[:3])
    else:
        parts.append(
            f"DeepAlpha 已执行 {mode} 分析路径，识别资产为 {asset}；当前方向判断为{direction_label}，置信度 {confidence}。"
        )
        parts.append(f"输入情报 {total_tweets} 条，进入判断的有效情报 {relevant_count} 条。")
    if errors:
        parts.append(f"抓取过程中记录到 {len(errors)} 个错误，已保留在响应的 crawl.errors 中。")
    return " ".join(part for part in parts if part)


def _ui_rows(decision: dict[str, Any], judgment: dict[str, Any], total: int, relevant: int, errors: list[Any]) -> list[list[str]]:
    rows = [
        ["资产识别", decision.get("asset", "unknown"), decision.get("why_this_route") or "基于问题路由器自动识别"],
        ["抓取/历史情报", f"{total} 条", f"进入信号判断 {relevant} 条；错误 {len(errors)} 个"],
        ["方向判断", judgment.get("market_direction_label") or "无明确方向", "证据不足或信号冲突时不强行给方向"],
        ["影响等级", f"{judgment.get('avg_impact', 0)}/5", "越高说明越可能形成市场冲击"],
    ]
    signal_count = judgment.get("signal_count") or {}
    if signal_count:
        rows.append(["信号分布", "；".join(f"{key}: {value}" for key, value in signal_count.items()), "检查方向是否集中"])
    if judgment.get("total_score") is not None:
        rows.append(["原油规则总分", f"{judgment['total_score']:+.2f}", "事件方向 × 强度 × 来源权重 × 置信度 × 时效权重"])
    if judgment.get("top_factors"):
        rows.append(["主要因子", _factor_text(judgment.get("top_factors") or []), "按绝对贡献排序"])
    if judgment.get("war_escalation_score") is not None:
        rows.append(["战争升级风险", f"{judgment['war_escalation_score']}/100", "口头冲突、军事部署、油轮事件、直接打击分层计分"])
    if judgment.get("conflict_notes"):
        rows.append(["冲突消解", "；".join(judgment["conflict_notes"][:2]), "多空信号并存时降低外推强度"])
    return rows


def _events_from_judgment(judgment: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for signal in judgment.get("top_signals") or []:
        structured = signal.get("structured_event") or {}
        if not signal.get("direction") and not signal.get("oil_rules"):
            continue
        body_parts = [
            str(signal.get("output_template") or signal.get("impact_reason") or "").strip(),
            str(signal.get("tweet_content") or "").replace("\n", " ")[:160],
        ]
        tags = [
            str(structured.get("factor") or signal.get("factor") or "factor"),
            str(structured.get("event_type") or signal.get("event_type") or "event"),
            str(signal.get("source_type") or "source"),
        ]
        events.append(
            {
                "title": signal.get("direction_label") or "原油规则信号",
                "body": " ".join(part for part in body_parts if part),
                "tags": tags,
            }
        )
    return events[:4]


def _events_from_tweets(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not tweets:
        return [{"title": "暂无高置信事件簇", "body": "本轮没有足够有效情报形成事件级证据链。", "tags": ["low_sample"]}]
    events = []
    for tweet in tweets[:4]:
        events.append(
            {
                "title": tweet.get("handle") or tweet.get("tweet_handle") or "未知来源",
                "body": str(tweet.get("content") or tweet.get("tweet_content") or "").replace("\n", " ")[:180],
                "tags": [str(tweet.get("_final_verdict") or tweet.get("direction_label") or "evidence")],
            }
        )
    return events


def _ui_signal_chips(decision: dict[str, Any], relevant_count: int, errors: list[Any]) -> list[dict[str, str]]:
    chips = [{"label": str(account).lstrip("@"), "provider": "x", "status": "success"} for account in decision.get("top_accounts", [])[:8]]
    chips.append({"label": "signal_judge", "provider": "local", "status": "success" if relevant_count else "error"})
    if errors:
        chips.append({"label": "crawler_errors", "provider": "runtime", "status": "error"})
    return chips


def _signals_from_judgment(judgment: dict[str, Any]) -> list[dict[str, Any]]:
    signals = []
    for signal in judgment.get("top_signals") or []:
        signals.append(
            {
                "source": signal.get("tweet_handle") or "",
                "direction": _direction_code(signal.get("direction")),
                "direction_label": signal.get("direction_label"),
                "confidence": signal.get("confidence", 0),
                "impact_level": signal.get("impact_level", 0),
                "reason": signal.get("impact_reason", ""),
                "content": signal.get("tweet_content", ""),
                "score": signal.get("score"),
                "factor": signal.get("factor"),
                "event_type": signal.get("event_type"),
                "source_type": signal.get("source_type"),
                "rules": signal.get("oil_rules") or [],
            }
        )
    return signals


def _evidence_text(judgment: dict[str, Any], relevant_count: int, confidence: float) -> str:
    parts = [f"有效情报 {relevant_count} 条", f"置信度 {confidence}", f"平均影响 {judgment.get('avg_impact', 0)}/5"]
    if judgment.get("total_score") is not None:
        parts.append(f"规则总分 {judgment['total_score']:+.2f}")
    if judgment.get("top_factors"):
        parts.append(f"主要因子 {_factor_text(judgment.get('top_factors') or [])}")
    return " / ".join(parts)


def _factor_text(items: list[dict[str, Any]]) -> str:
    return "；".join(
        f"{item.get('factor')} {float(item.get('score') or 0):+.1f}"
        for item in items[:4]
    )


def _ai_context_for_oil(
    *,
    query: str,
    mode: str,
    decision: dict[str, Any],
    judgment: dict[str, Any],
    top_tweets: list[dict[str, Any]],
    errors: list[Any],
) -> dict[str, Any]:
    from deepalpha.oil_factor_rules import build_oil_ai_context

    return build_oil_ai_context(
        query=query,
        decision=decision,
        tweets=top_tweets,
        judgment=judgment,
        mode=mode,
        errors=errors,
    )


def _direction_code(value: Any) -> str:
    text = str(value or "").lower()
    if "bullish" in text:
        return "bullish"
    if "bearish" in text:
        return "bearish"
    return "neutral"


def _empty_judgment() -> dict[str, Any]:
    return {
        "market_direction": None,
        "market_direction_label": None,
        "aggregate_confidence": 0.0,
        "signal_count": {},
        "avg_impact": 0.0,
        "top_signals": [],
        "details": [],
    }


def _failure_response(query: str, error: str) -> dict[str, Any]:
    return {
        "query": query,
        "asset": "unknown",
        "direction": "neutral",
        "confidence": 0,
        "summary": f"分析失败：{error}",
        "signals": [],
        "disclaimer": DISCLAIMER,
        "mode": "error",
        # Keep the same top-level shape as a successful response so consumers
        # can read crawl.errors / graph.node_count / decision without KeyError
        # on the failure path.
        "decision": {},
        "crawl": {"total": 0, "errors": [], "csv_path": None},
        "graph": {"node_count": 0, "edge_count": 0, "output_file": None, "tweet_count": 0},
        "stats": {"total": 0, "relevant": 0, "graph_nodes": 0, "graph_edges": 0},
        "plan": {"core_variable": query, "time_window": "-", "sources": [], "signals": []},
        "report": {
            "title": f"{query}：DeepAlpha 分析失败",
            "lead": f"分析失败：{error}",
            "rows": [["错误", error, "接口已返回结构化失败结果"]],
            "events": [],
            "direction": "无明确方向",
            "evidence": "无",
            "risk": DISCLAIMER,
        },
    }


def _runtime_args(options: AnalyzeOptions) -> SimpleNamespace:
    return SimpleNamespace(
        ai=False,
        new_cleaner=options.new_cleaner,
        no_clean=False,
        no_judge=False,
        no_graph=False,
        graph_file="./graph_data/关系图谱.json",
        graph_current_only=False,
        view_graph=False,
        graph_port=8080,
        cookie_file=options.cookie_file,
        browser=options.browser,
        headless=options.headless,
        delay=options.delay,
        output=None,
        debug=options.debug,
        event_pipeline=False,
    )


def _options_from_env(mode: str | None, timeout_seconds: int | None) -> AnalyzeOptions:
    return AnalyzeOptions(
        mode=(mode or os.getenv("DEEPALPHA_ANALYZE_MODE") or "crawl").strip().lower(),
        timeout_seconds=_env_int("DEEPALPHA_ANALYZE_TIMEOUT_SECONDS", timeout_seconds if timeout_seconds is not None else 420),
        cookie_file=os.getenv("DEEPALPHA_COOKIE_FILE", "cookies/browser/x_cookie.json"),
        browser=os.getenv("DEEPALPHA_BROWSER", "chrome"),
        headless=os.getenv("DEEPALPHA_HEADLESS", "1").lower() not in {"0", "false", "no"},
        delay=_env_int("DEEPALPHA_CRAWL_DELAY", 0),
        accounts_per_round=_env_int("DEEPALPHA_WEB_ACCOUNTS_PER_ROUND", 5),
        tweets_per_account=_env_int("DEEPALPHA_WEB_TWEETS_PER_ACCOUNT", 20),
        search_tasks_per_round=_env_int("DEEPALPHA_WEB_SEARCH_TASKS", 2),
        tweets_per_search=_env_int("DEEPALPHA_WEB_TWEETS_PER_SEARCH", 30),
        new_cleaner=os.getenv("DEEPALPHA_NEW_CLEANER", "1").lower() not in {"0", "false", "no"},
        debug=os.getenv("DEEPALPHA_DEBUG", "0").lower() in {"1", "true", "yes"},
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _multiprocessing_context():
    methods = mp.get_all_start_methods()
    if "fork" in methods:
        return mp.get_context("fork")
    return mp.get_context(methods[0])


def _apply_web_crawl_budget(decision: dict[str, Any], options: AnalyzeOptions) -> None:
    decision["accounts_per_round"] = max(0, options.accounts_per_round)
    decision["tweets_per_account"] = max(1, options.tweets_per_account)
    decision["search_tasks_per_round"] = max(0, options.search_tasks_per_round)
    decision["tweets_per_search"] = max(1, options.tweets_per_search)
    if options.accounts_per_round <= 0:
        decision["top_accounts"] = []
    if options.search_tasks_per_round <= 0:
        decision["crawl_tasks"] = []


def _terminate_process_tree(process) -> None:
    if process.pid and hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    process.terminate()


def _enter_project_root() -> None:
    os.chdir(PROJECT_ROOT)
