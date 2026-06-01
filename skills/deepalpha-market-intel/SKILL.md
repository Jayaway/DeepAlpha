---
name: deepalpha-market-intel
description: Run DeepAlpha market intelligence analysis for questions such as "今天油价会涨吗？", "BTC 会涨吗？", "黄金走势如何？", or any request to interpret market direction, confidence, evidence, X/Twitter intelligence, the relation graph, or risk notes. Use when the user is inside a DeepAlpha checkout and wants a data-backed market read instead of an invented one.
---

# DeepAlpha Market Intel

Use DeepAlpha as the source of truth for market-intelligence questions. **Never fabricate
market direction.** Call the local analysis pipeline, then summarize the returned
structured result.

This skill runs **against the local project** (`deepalpha_adapter.analyze_market_query`).
It does not depend on any remote service.

## Quick Start

From a DeepAlpha checkout, the bundled script is the callable entry point:

```bash
python skills/deepalpha-market-intel/scripts/deepalpha_analyze.py "今天油价会涨吗？"
```

- Default mode is **history**: it analyzes the local CSV 历史库 in `./抓取的信息/`.
  No browser, no cookies, no network — fast and always runnable.
- Add `--crawl` for a full realtime X/Twitter crawl (needs Chrome + a valid
  `cookies/browser/x_cookie.json`):

  ```bash
  python skills/deepalpha-market-intel/scripts/deepalpha_analyze.py "油价会涨吗？" --crawl
  ```

- Add `--json` for the full structured response (useful for wiring UI or pipelines):

  ```bash
  python skills/deepalpha-market-intel/scripts/deepalpha_analyze.py "BTC 会涨吗？" --json
  ```

If the script is run from outside the project, point it at the root:

```bash
python /path/to/DeepAlpha/skills/deepalpha-market-intel/scripts/deepalpha_analyze.py \
  "黄金走势如何？" --project-root /path/to/DeepAlpha
# or: export DEEPALPHA_HOME=/path/to/DeepAlpha
```

You may also call the adapter directly, or use the project CLI:

```bash
python -c "from deepalpha_adapter import analyze_market_query; print(analyze_market_query('今天油价会涨吗？', mode='history', timeout_seconds=0))"
python run_v2.py "油价会涨吗？"          # history analysis
python run_v2.py "油价会涨吗？" --crawl  # realtime crawl
```

## Workflow

1. Identify the user query and preserve the original wording.
2. Run `scripts/deepalpha_analyze.py "<query>"` (history by default; add `--crawl`
   only when the user explicitly wants fresh live data and Chrome+cookies are set up).
3. Read these fields first (see `references/api_contract.md` for the full shape):
   - `asset`
   - `direction` (`bullish` / `bearish` / `neutral`)
   - `confidence`
   - `summary`
   - `mode` (`history` / `crawl` / `*_fallback` / `error`)
   - `stats.total` / `stats.relevant`
   - `signals` (top evidence)
   - `crawl.errors`
   - `graph.node_count` / `graph.edge_count`
   - `disclaimer`
4. Report the result in Chinese unless the user asks otherwise.
5. Always include the disclaimer or an equivalent risk note.

## Output Shape

Short answer template:

```text
结论：{direction}，置信度 {confidence}
资产：{asset}
摘要：{summary}
关键证据：{signals}
风险提示：{disclaimer}
```

Debug / deployment check:

```text
mode={mode}
stats.total={stats.total} / stats.relevant={stats.relevant}
crawl.errors={len(crawl.errors)}
graph={graph.node_count}/{graph.edge_count}
```

## Guardrails

- Treat `neutral` and low confidence as a real result, not a failure.
- If `crawl.errors` is non-empty, mention it briefly and avoid overconfident conclusions.
- If `mode` ends in `_fallback` (e.g. `timeout_fallback`, `crawl_empty_fallback`),
  say the live crawl did not complete and the result came from history-library fallback.
- Default to **history mode** when in doubt; only crawl when the user wants live data.
- Never write API keys, cookies, or X session data into commands or files.
- Do not touch `scraper/`, server, Nginx, SSH, Chrome, or cookie configuration unless
  the user explicitly asks for crawl/deployment work.

## References

- `references/api_contract.md` — the actual local adapter response shape.
