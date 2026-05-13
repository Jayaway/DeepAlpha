# DeepAlpha API Contract

## Endpoint

```text
POST https://deepalpha.cloud/api/analyze
Content-Type: application/json

{"query":"今天油价会涨吗？"}
```

## Stable Fields

```json
{
  "query": "今天油价会涨吗？",
  "asset": "oil",
  "direction": "bullish | bearish | neutral",
  "confidence": 0.2,
  "summary": "中文分析摘要",
  "signals": [],
  "disclaimer": "本系统输出仅用于信息分析与项目演示，不构成任何投资建议。",
  "mode": "crawl | history | timeout_fallback | error",
  "crawl": {
    "total": 0,
    "errors": [],
    "csv_path": "./抓取的信息/..."
  },
  "graph": {
    "node_count": 80,
    "edge_count": 78,
    "nodes": [],
    "edges": []
  }
}
```

## Interpretation Rules

- `neutral` means insufficient or conflicting evidence, not system failure.
- `confidence` is an internal confidence score; avoid making investment recommendations from it.
- `mode=timeout_fallback` means live crawl did not finish and historical/fallback analysis was used.
- `crawl.errors` should be surfaced in diagnostics.
- `graph.node_count` / `graph.edge_count` are optional; clients should fall back to `len(graph.nodes)` and `len(graph.edges)`.
