# Build the workspace app and serve it together with the static site.
# Build context: repository root.
FROM node:22-alpine AS web
WORKDIR /workspace/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM nginx:1.27-alpine
ENV API_UPSTREAM=http://host.docker.internal:8787
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY site/ /usr/share/nginx/html/
COPY --from=web /workspace/apps/web/dist/ /usr/share/nginx/html/app/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
