#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastAPI entrypoint for DeepAlpha Cloud."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deepalpha_adapter import DISCLAIMER, analyze_market_query
from deepalpha.graph_engine import DEFAULT_GRAPH_FILE


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"

app = FastAPI(title="DeepAlpha", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    query: str | None = Field(default=None)
    question: str | None = Field(default=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "deepalpha"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return health()


@app.get("/api/graph")
def api_graph() -> dict:
    graph_path = PROJECT_ROOT / DEFAULT_GRAPH_FILE
    if not graph_path.exists():
        return {"query": None, "generated": None, "nodes": [], "edges": []}
    try:
        import json

        return json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"query": None, "generated": None, "nodes": [], "edges": [], "error": str(exc)}


@app.post("/api/analyze")
async def api_analyze(payload: AnalyzeRequest) -> JSONResponse:
    query = (payload.query or payload.question or "").strip()
    if not query:
        return JSONResponse(
            status_code=400,
            content={
                "query": "",
                "asset": "unknown",
                "direction": "neutral",
                "confidence": 0,
                "summary": "分析失败：query 不能为空",
                "signals": [],
                "disclaimer": DISCLAIMER,
            },
        )

    result = await run_in_threadpool(analyze_market_query, query)
    return JSONResponse(content=result)


if WEB_ROOT.exists():
    app.mount("/", StaticFiles(directory=str(WEB_ROOT), html=True), name="web")
