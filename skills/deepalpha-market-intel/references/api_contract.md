# DeepAlpha Adapter Contract

The skill calls the **local** project, not a remote API. The callable surface is:

```python
from deepalpha_adapter import analyze_market_query

analyze_market_query(query: str, mode: str | None = None, timeout_seconds: int | None = None) -> dict
```

- `mode`: `"history"` (local CSV 历史库, no browser) or `"crawl"` (realtime Selenium).
  Defaults to env `DEEPALPHA_ANALYZE_MODE`, else `"crawl"`. The skill script defaults
  to `"history"` for safety.
- `timeout_seconds`: `0` runs synchronously (history); `>0` guards the crawl in a
  subprocess and falls back to history on timeout.

## Response Fields

Stable top-level fields (history and crawl share the same shape):

```json
{
  "query": "油价会涨吗？",
  "asset": "oil",
  "direction": "bullish | bearish | neutral",
  "confidence": 0.29,
  "summary": "中文分析摘要",
  "signals": [
    {
      "source": "@Reuters",
      "direction": "bullish",
      "direction_label": "利多原油",
      "confidence": 0.6,
      "impact_level": 3,
      "reason": "...",
      "content": "...",
      "score": 1.2,
      "factor": "supply",
      "event_type": "...",
      "source_type": "...",
      "rules": []
    }
  ],
  "disclaimer": "本系统输出仅用于信息分析与项目演示，不构成任何投资建议。",
  "mode": "history | crawl | timeout_fallback | crawl_empty_fallback | error_fallback | error",
  "decision": { "asset": "oil", "top_accounts": [], "...": "intel router 路由结果" },
  "crawl": {
    "total": 0,
    "errors": [],
    "csv_path": "./抓取的信息/...  (crawl 模式写入时)"
  },
  "stats": {
    "total": 313,
    "relevant": 80,
    "graph_nodes": 80,
    "graph_edges": 96
  },
  "plan":   { "core_variable": "...", "time_window": "...", "sources": [], "signals": [] },
  "report": { "title": "...", "lead": "...", "rows": [], "events": [], "direction": "...", "evidence": "...", "risk": "...", "top_tweets": [] },
  "graph":  { "node_count": 80, "edge_count": 96, "output_file": "./graph_data/关系图谱.json", "tweet_count": 313 },
  "ai_context": { "...": "仅当 asset == oil 时存在" }
}
```

> 注意：`graph` 是**摘要对象**，只含 `node_count` / `edge_count` / `output_file` / `tweet_count`，
> **不含 `nodes` / `edges` 数组**——完整节点和边写在 `output_file` 指向的 JSON 文件里。
> `stats.graph_nodes` / `stats.graph_edges` 直接镜像 `graph.node_count` / `graph.edge_count`。

`plan` / `report` / `ai_context` exist to feed the web UI; most answers only need
`asset`, `direction`, `confidence`, `summary`, `signals`, `stats`, `mode`, `disclaimer`.

## Interpretation Rules

- `neutral` means insufficient or conflicting evidence, not system failure.
- `confidence` is an internal score; do not turn it into an investment recommendation.
- `mode` ending in `_fallback` means the live crawl did not finish and history/fallback
  analysis was used — say so.
- Surface `crawl.errors` in diagnostics.
- For graph size use `graph.node_count` / `graph.edge_count` (or the mirrored
  `stats.graph_nodes` / `stats.graph_edges`). There are no inline `graph.nodes` /
  `graph.edges` arrays — read the `output_file` if you need them.
- On hard failure the adapter still returns a structured object with `mode: "error"`.
  The failure object now carries the same top-level keys (`decision`, `crawl`, `graph`,
  `stats`, `plan`, `report`) as a success, so consumers can use direct access safely.
  The skill script exits non-zero when `mode == "error"`.

## Notes

- History mode reads CSVs from `./抓取的信息/` and writes the graph to
  `./graph_data/关系图谱.json`.
- The adapter `chdir`s into the project root, so relative paths resolve there.
- The previously documented `POST https://deepalpha.cloud/api/analyze` endpoint is not
  used by this skill; the skill runs entirely against the local checkout.
