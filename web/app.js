const homeScreen = document.querySelector("#homeScreen");
const analysisScreen = document.querySelector("#analysisScreen");
const homeForm = document.querySelector("#homeForm");
const homeQuery = document.querySelector("#homeQuery");
const queryInput = document.querySelector("#queryInput");
const queryForm = document.querySelector("#queryForm");
const chipGrid = document.querySelector("#chipGrid");
const signalRows = document.querySelector("#signalRows");
const eventGrid = document.querySelector("#eventGrid");
const modeText = document.querySelector("#modeText");
const installSkillButton = document.querySelector("#installSkillButton");
const skillModal = document.querySelector("#skillModal");
const closeSkillModal = document.querySelector("#closeSkillModal");
const defaultRemoteApi = "https://deepalpha.cloud";
const apiParam = new URLSearchParams(window.location.search).get("api");
const apiBase = apiParam || (location.protocol === "file:" ? defaultRemoteApi : "");

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeQuery(value) {
  return value.trim() || "石油价格会涨吗";
}

function formatDirection(value) {
  const text = String(value || "").toLowerCase();
  if (text === "bullish") return "偏利多";
  if (text === "bearish") return "偏利空";
  if (text === "neutral") return "中性 / 暂无明确方向";
  return value || "暂无明确方向";
}

function formatPercent(value) {
  const num = Number(value || 0);
  if (num > 1) return `${num.toFixed(2)}`;
  return `${Math.round(num * 100)}%`;
}

function graphCounts(graph, stats) {
  const nodes = graph?.node_count ?? graph?.nodes?.length ?? stats?.graph_nodes ?? 0;
  const edges = graph?.edge_count ?? graph?.edges?.length ?? stats?.graph_edges ?? 0;
  return { nodes, edges };
}

function statusLabel(mode) {
  if (mode === "crawl") return "实时抓取";
  if (String(mode || "").includes("fallback")) return "回退分析";
  if (mode === "history") return "历史库";
  if (mode === "error") return "分析失败";
  return "分析完成";
}

function setLoading(query) {
  queryInput.value = query;
  byId("reportTitle").textContent = `${query}：DeepAlpha 正在分析`;
  byId("coreVariable").textContent = "正在理解问题";
  byId("timeWindow").textContent = "实时抓取、清洗、图谱与报告生成中";
  byId("sourceLine").textContent = apiBase ? `${apiBase}/api/analyze` : "/api/analyze";
  byId("sourceCount").textContent = "0";
  byId("successCount").textContent = "0";
  byId("failedCount").textContent = "0";
  byId("failureCount").textContent = "0";
  byId("directionText").textContent = "生成中";
  byId("evidenceText").textContent = "等待分析结果";
  byId("riskText").textContent = "等待分析结果";
  byId("leadText").textContent = "正在调用 DeepAlpha 真实分析链路，请稍候。";
  chipGrid.innerHTML = "";
  signalRows.innerHTML = "";
  eventGrid.innerHTML = "";
  modeText.textContent = "实时分析";
}

function setError(query, message) {
  byId("reportTitle").textContent = `${query}：分析请求失败`;
  byId("leadText").textContent = message;
  byId("directionText").textContent = "无法生成";
  byId("evidenceText").textContent = "请检查线上 /api/analyze 响应或浏览器网络面板";
  byId("riskText").textContent = "接口失败时不输出方向判断。";
  signalRows.innerHTML = `
    <tr>
      <td>API</td>
      <td>${escapeHtml(apiBase || location.origin)}</td>
      <td>${escapeHtml(message)}</td>
    </tr>
  `;
  eventGrid.innerHTML = "";
  modeText.textContent = "离线";
}

async function fetchAnalysis(query) {
  const response = await fetch(`${apiBase}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "分析接口调用失败");
  }
  return data;
}

function renderAnalysis(data) {
  const plan = data.plan || {};
  const stats = data.stats || {};
  const report = data.report || {};
  const crawl = data.crawl || {};
  const graph = data.graph || {};
  const graphStat = graphCounts(graph, stats);
  const sourceList = plan.sources || data.decision?.selected_accounts || data.decision?.top_accounts || [];
  const signals = normalizeSignals(data, plan);
  const rows = normalizeRows(data, report, crawl, graphStat);
  const events = normalizeEvents(data, report);
  const lead = data.summary || report.lead || "分析完成，但没有返回摘要。";
  const directionText = report.direction || formatDirection(data.direction);
  const evidenceText =
    report.evidence ||
    `资产 ${data.asset || "unknown"} / 置信度 ${formatPercent(data.confidence)} / 图谱 ${graphStat.nodes} 节点 ${graphStat.edges} 关系`;

  queryInput.value = data.query || "";
  byId("reportTitle").textContent = report.title || `${data.query}：DeepAlpha 情报分析`;
  byId("coreVariable").textContent = plan.core_variable || `${data.query || "-"} / asset=${data.asset || "unknown"}`;
  byId("timeWindow").textContent = plan.time_window || `${statusLabel(data.mode)} · CSV ${crawl.csv_path || "未返回路径"}`;
  byId("sourceLine").textContent = sourceList.map((item) => String(item).replace(/^@/, "")).join(", ") || "DeepAlpha realtime pipeline";
  byId("sourceCount").textContent = String(signals.length);
  byId("successCount").textContent = String(signals.filter((item) => item.status !== "error").length);
  byId("failedCount").textContent = String(signals.filter((item) => item.status === "error").length);
  byId("failureCount").textContent = String(signals.filter((item) => item.status === "error").length);
  byId("leadText").textContent = lead;
  byId("directionText").textContent = directionText;
  byId("evidenceText").textContent = evidenceText;
  byId("riskText").textContent = report.risk || data.disclaimer || "本系统输出仅用于信息分析与项目演示，不构成任何投资建议。";
  modeText.textContent = `${statusLabel(data.mode)} ${crawl.total ?? stats.total ?? 0} 条 / 错误 ${(crawl.errors || []).length}`;

  chipGrid.innerHTML = signals
    .map(
      (signal) =>
        `<span class="chip ${signal.status === "error" ? "chip-error" : ""}">${escapeHtml(signal.label || signal.source || signal.provider || "signal")}</span>`,
    )
    .join("");

  signalRows.innerHTML = rows
    .map(
      ([signal, value, meaning]) => `
        <tr>
          <td>${escapeHtml(signal)}</td>
          <td>${escapeHtml(value)}</td>
          <td>${escapeHtml(meaning)}</td>
        </tr>
      `,
    )
    .join("");

  eventGrid.innerHTML = events
    .map(
      (event) => `
        <div class="event-card">
          <strong>${escapeHtml(event.title)}</strong>
          <p>${escapeHtml(event.body)}</p>
          <div class="tag-row">${(event.tags || []).map((tag) => `<span class="mini-tag">${escapeHtml(tag)}</span>`).join("")}</div>
        </div>
      `,
    )
    .join("");
}

function normalizeSignals(data, plan) {
  const chips = [];
  if (Array.isArray(plan.signals)) chips.push(...plan.signals);
  if (Array.isArray(data.signals)) {
    for (const signal of data.signals) {
      chips.push({
        label: signal.source || signal.direction_label || signal.direction || "signal",
        status: signal.direction === "neutral" ? "error" : "success",
      });
    }
  }
  if (!chips.length) {
    chips.push({ label: "intent_router", status: "success" });
    chips.push({ label: "crawler", status: data.mode === "crawl" ? "success" : "error" });
    chips.push({ label: "report", status: data.summary ? "success" : "error" });
  }
  return chips;
}

function normalizeRows(data, report, crawl, graphStat) {
  if (Array.isArray(report.rows) && report.rows.length) return report.rows;
  const errors = crawl.errors || [];
  return [
    ["资产识别", data.asset || "unknown", `方向：${formatDirection(data.direction)} / 置信度：${formatPercent(data.confidence)}`],
    ["实时抓取", `${crawl.total ?? 0} 条`, errors.length ? `错误 ${errors.length} 个：${errors.slice(0, 2).join("；")}` : "抓取链路正常返回"],
    ["关系图谱", `${graphStat.nodes} 节点 / ${graphStat.edges} 关系`, "由本次分析生成 graph_data/关系图谱.json"],
    ["报告摘要", data.mode || "unknown", data.summary || "暂无摘要"],
  ];
}

function normalizeEvents(data, report) {
  if (Array.isArray(report.events) && report.events.length) return report.events;
  if (Array.isArray(data.signals) && data.signals.length) {
    return data.signals.slice(0, 4).map((signal) => ({
      title: signal.source || signal.direction_label || "关键证据",
      body: signal.content || signal.reason || "信号没有返回正文。",
      tags: [signal.direction_label || signal.direction || "signal", `impact ${signal.impact_level ?? 0}`],
    }));
  }
  return [{ title: "暂无高影响信号", body: data.summary || "本轮分析没有形成可展示的高影响证据。", tags: [data.direction || "neutral"] }];
}

async function showAnalysis(rawQuery) {
  const query = normalizeQuery(rawQuery);
  homeScreen.classList.add("hidden");
  analysisScreen.classList.remove("hidden");
  setLoading(query);
  queryInput.focus();

  try {
    const data = await fetchAnalysis(query);
    renderAnalysis(data);
  } catch (error) {
    setError(query, error.message);
  }
}

function showHome() {
  analysisScreen.classList.add("hidden");
  homeScreen.classList.remove("hidden");
  modeText.textContent = "首页";
  homeQuery.value = "";
  homeQuery.focus();
}

function openSkillModal() {
  if (!skillModal) return;
  skillModal.classList.add("visible");
  skillModal.setAttribute("aria-hidden", "false");
}

function closeSkillModalPanel() {
  if (!skillModal) return;
  skillModal.classList.remove("visible");
  skillModal.setAttribute("aria-hidden", "true");
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  document.body.appendChild(textArea);
  textArea.select();
  document.execCommand("copy");
  textArea.remove();
}

function bindSkillModal() {
  if (!installSkillButton || !skillModal || !closeSkillModal) return;

  installSkillButton.addEventListener("click", openSkillModal);
  closeSkillModal.addEventListener("click", closeSkillModalPanel);
  skillModal.addEventListener("click", (event) => {
    if (event.target === skillModal) closeSkillModalPanel();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSkillModalPanel();
  });

  skillModal.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const originalText = button.textContent;
      try {
        await copyText(button.dataset.copy || "");
        button.textContent = "已复制";
        button.classList.add("copied");
      } catch (error) {
        button.textContent = "复制失败";
      }

      window.setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove("copied");
      }, 1600);
    });
  });
}

homeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  showAnalysis(homeQuery.value);
});

queryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  showAnalysis(queryInput.value);
});

document.querySelector("#newQuestion").addEventListener("click", () => {
  showHome();
});

bindSkillModal();
