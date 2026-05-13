#!/usr/bin/env python3
"""Call the DeepAlpha analyze API and print structured JSON."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_API_URL = "https://deepalpha.cloud/api/analyze"


def analyze(query, api_url, timeout):
    payload = json.dumps({"query": query}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="Run DeepAlpha market intelligence analysis.")
    parser.add_argument("query", help="Market question, e.g. 今天油价会涨吗？")
    parser.add_argument("--api-url", default=os.getenv("DEEPALPHA_API_URL", DEFAULT_API_URL))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("DEEPALPHA_TIMEOUT", "480")))
    parser.add_argument("--compact", action="store_true", help="Print a concise human-readable summary.")
    args = parser.parse_args()

    try:
        data = analyze(args.query, args.api_url, args.timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "query": args.query}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.compact:
        crawl = data.get("crawl") or {}
        graph = data.get("graph") or {}
        node_count = graph.get("node_count")
        edge_count = graph.get("edge_count")
        if node_count is None:
            node_count = len(graph.get("nodes") or [])
        if edge_count is None:
            edge_count = len(graph.get("edges") or [])
        print(f"结论：{data.get('direction')} / 置信度 {data.get('confidence')}")
        print(f"资产：{data.get('asset')}")
        print(f"模式：{data.get('mode')} / 抓取 {crawl.get('total', 0)} 条 / 图谱 {node_count} 节点 {edge_count} 关系")
        print(f"摘要：{data.get('summary', '')}")
        print(f"风险提示：{data.get('disclaimer', '')}")
        return 0

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
