# Deploy · 工作台与静态站点

这套镜像把 **主站 + `/app/` 工作台 + `/models/` `/live/` 子页面** 一起交给 Nginx，并把 `/api/` 反代到本地 Python runtime。

## 快速启动

```bash
# 在仓库根目录
docker compose -f deploy/docker-compose.yml up --build
```

打开：

- `http://127.0.0.1:8080/`：主站
- `http://127.0.0.1:8080/app/`：React 工作台
- `http://127.0.0.1:8080/models/`、`/live/`、`/agent/`（legacy）

工作台本身是 `SIM · STATIC`，不依赖 runtime；没有启动 Python 时只有 `/live/` 与模型高级页的 **Probe/真实 API** 会不可用，工作台仍能打开。

## Runtime / 密钥

Nginx 将 `/api/` 代理到：

```yaml
environment:
  API_UPSTREAM: http://host.docker.internal:8787
```

Linux 通过 `extra_hosts: host.docker.internal:host-gateway` 访问宿主机。若 runtime 也在这个 compose 网络中，把 `API_UPSTREAM` 改为 `http://runtime:8787` 并加入同一 network。

启动本地 runtime（宿主机）：

```bash
python -m research_agent.runtime --port 8787
```

**密钥只放在 runtime 的 env / session 内存**，不要写进 `docker-compose.yml`、Nginx 模板或前端构建变量。前端构建产物里只有静态配置和 SIM 数据。

## 部署在其他域名 / 子路径

- 镜像默认 Nginx 根路径为 `/`，工作台在 `/app/`。若挂在反向代理的 `/research-agent/` 子路径，需要在外层代理重写，或重新配置 Nginx 的 root/路径；工作台内部使用相对资源（`base: "./"`），`/app/` 子目录可直接工作。
- `VITE_SITE_BASE` 控制工作台内到 `/models/`、`/live/` 的链接前缀，默认 `../`。若改变目录层级，在构建前设置它并重新构建。
- HTTPS 由外层反代（Caddy/Traefik/云负载均衡）终止；本容器只提供 HTTP 80。

## 静态托管（无 Docker）

```bash
cd apps/web && npm ci && npm run build:site && cd ../..
# 将 site/ 作为静态根目录
python -m http.server 8000 --directory site
# http://127.0.0.1:8000/app/
```

GitHub Pages 由 `.github/workflows/pages.yml` 执行同样的 app 构建；`site/agent/` 保留为 legacy，不再从主站链接。

## 不在镜像里

- 没有真实模型调用、MCP transport、实验执行器或 claim 签名端点；
- 没有数据库/Redis；工作台状态只存在浏览器 localStorage；
- 没有多用户鉴权；不要把 `/api/` 暴露到公网而未做 runtime 自身的访问控制。
