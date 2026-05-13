---
name: deepalpha-market-intel
description: Run DeepAlpha market intelligence analysis for questions such as "今天油价会涨吗？", "BTC 会涨吗？", "黄金走势如何？", or requests to interpret market direction, confidence, evidence, crawl results, graph output, X/Twitter intelligence, risk notes, or DeepAlpha API responses. Use when Codex should call or guide a DeepAlpha Cloud/Hermes/OpenClaw/GitHub workflow rather than inventing market analysis from scratch.
---

# DeepAlpha Market Intel

Use DeepAlpha as the source of truth for market-intelligence questions. Do not fabricate market direction. Call the DeepAlpha API or the local adapter, then summarize the returned structured result.

## Quick Start

Prefer the bundled script:

```bash
python scripts/deepalpha_analyze.py "今天油价会涨吗？"
```

The script calls `DEEPALPHA_API_URL` when set, otherwise:

```text
https://deepalpha.cloud/api/analyze
```

Use local project code only when the user is inside a DeepAlpha checkout and explicitly wants local execution:

```bash
python -c "from deepalpha_adapter import analyze_market_query; print(analyze_market_query('今天油价会涨吗？'))"
```

## Workflow

1. Identify the user query and preserve the original wording.
2. Call DeepAlpha through `scripts/deepalpha_analyze.py` or the local `deepalpha_adapter.analyze_market_query`.
3. Read these fields first:
   - `asset`
   - `direction`
   - `confidence`
   - `summary`
   - `signals`
   - `crawl.total`
   - `crawl.errors`
   - `graph.node_count` / `graph.edge_count` or `graph.nodes` / `graph.edges`
   - `disclaimer`
4. Report the result in Chinese unless the user asks otherwise.
5. Always include the disclaimer or an equivalent risk note.

## Output Shape

For short answers:

```text
结论：{direction}，置信度 {confidence}
资产：{asset}
摘要：{summary}
关键证据：{signals}
风险提示：{disclaimer}
```

For debugging or deployment checks, include:

```text
mode={mode}
crawl.total={crawl.total}
crawl.errors={len(crawl.errors)}
graph={node_count}/{edge_count}
csv={crawl.csv_path}
```

## Guardrails

- Treat `neutral` and low confidence as a real result, not a failure.
- If `crawl.errors` is non-empty, mention it briefly and avoid overconfident conclusions.
- If the API times out or returns `timeout_fallback`, say the live crawl did not complete and the result came from fallback analysis.
- Never write API keys, cookies, or X session data into commands or files.
- Do not change server, Nginx, SSH, Chrome, or cookie configuration unless the user explicitly asks for deployment work.

## References

- Read `references/api_contract.md` when adapting a client, UI, or GitHub/Hermes/OpenClaw integration.
