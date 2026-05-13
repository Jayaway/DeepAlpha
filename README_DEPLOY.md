# DeepAlpha Cloud Deploy

本部署说明用于把本地 DeepAlpha 项目同步到已经配置好的云服务器：

- 站点：`https://deepalpha.cloud`
- 服务器目录：`/opt/deepalpha`
- 后端监听：`127.0.0.1:8000`
- systemd 服务：`deepalpha`
- Nginx/HTTPS：保持现有配置，不开放 8000 端口

## 本次接入内容

- `main.py`：FastAPI 入口，提供 `/health`、`/api/analyze`、`/api/graph`，并托管 `web/` 页面。
- `deepalpha_adapter.py`：把本地 DeepAlpha 完整分析链路封装成 `analyze_market_query(query)`。
- `web/`：本地新版网页，线上首页、Docs、Slides、Graph 都从这里提供。
- `requirements.txt`：补充 FastAPI/Uvicorn 运行依赖。

## 运行模式

默认模式会尝试实时抓取：

```bash
DEEPALPHA_ANALYZE_MODE=crawl
```

如果服务器暂时没有浏览器、Cookie 或抓取环境，可以切换成历史库模式：

```bash
DEEPALPHA_ANALYZE_MODE=history
```

常用环境变量：

```bash
DEEPALPHA_ANALYZE_TIMEOUT_SECONDS=420
DEEPALPHA_COOKIE_FILE=cookies/browser/x_cookie.json
DEEPALPHA_BROWSER=chrome
DEEPALPHA_HEADLESS=1
DEEPALPHA_CRAWL_DELAY=0
DEEPALPHA_WEB_ACCOUNTS_PER_ROUND=5
DEEPALPHA_WEB_TWEETS_PER_ACCOUNT=20
DEEPALPHA_WEB_SEARCH_TASKS=2
DEEPALPHA_WEB_TWEETS_PER_SEARCH=30
```

线上默认恢复完整抓取预算：5 个账号、每个 20 条，外加 2 个搜索任务、每个 30 条。Nginx 的 `proxy_read_timeout` 建议不低于 480 秒，否则浏览器可能先于后端超时。

不要把 API Key、Cookie 内容或 token 写进代码。Cookie 文件只放服务器本地。

## 上传

建议从本地执行：

```bash
rsync -av \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".DS_Store" \
  ./ root@43.112.114.255:/opt/deepalpha/
```

如果使用 `scp`，也可以只上传必要目录和文件：

```bash
scp -r main.py deepalpha_adapter.py requirements.txt deepalpha deepalpha_runtime scraper web root@43.112.114.255:/opt/deepalpha/
```

## 服务器安装与重启

```bash
cd /opt/deepalpha
source venv/bin/activate
pip install -r requirements.txt
systemctl restart deepalpha
```

查看日志：

```bash
journalctl -u deepalpha -f
```

## 验收

本地函数：

```bash
python3 -c "from deepalpha_adapter import analyze_market_query; print(analyze_market_query('今天油价会涨吗？'))"
```

健康检查：

```bash
curl https://deepalpha.cloud/health
```

应返回：

```json
{"status":"ok","service":"deepalpha"}
```

分析接口：

```bash
curl -X POST https://deepalpha.cloud/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query":"今天油价会涨吗？"}'
```

返回中应包含真实路由、抓取/历史库分析结果，而不是固定 demo response。
