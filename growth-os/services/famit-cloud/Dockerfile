# Famit Cloud control plane — self-hostable image.
#
# This control plane SHELLS OUT to the `docker` CLI to run container workloads, so the image ships
# docker-cli and the host's Docker socket must be mounted at runtime (docker-out-of-docker):
#   docker run -v /var/run/docker.sock:/var/run/docker.sock -p 3024:3024 \
#     -e CLOUD_INTERNAL_TOKEN=... -e CLOUD_SECRET_KEY=... -e CLOUD_BIND=0.0.0.0 famit-cloud
#
# Build CONTEXT is the growth-os monorepo root (it needs the workspace + @growth-os/otel):
#   docker build -f services/famit-cloud/Dockerfile -t famit-cloud .
#
# Multi-stage: build with pnpm (deploys a self-contained node_modules), run on a slim base.

# ---- build ------------------------------------------------------------------------------------
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
# Copy the workspace manifests first for a cached install layer.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* tsconfig.base.json ./
COPY packages ./packages
COPY services/famit-cloud ./services/famit-cloud
RUN pnpm install --frozen-lockfile=false --filter @growth-os/famit-cloud... \
 && pnpm --filter @growth-os/famit-cloud build \
 # Produce a self-contained deploy tree (dist + pruned prod node_modules) at /app.
 && pnpm --filter @growth-os/famit-cloud deploy --prod --legacy /app

# ---- runtime ----------------------------------------------------------------------------------
FROM node:22-alpine AS runtime
# docker-cli lets the control plane manage workload containers via the mounted socket.
RUN apk add --no-cache docker-cli wget
WORKDIR /app
COPY --from=build /app /app
ENV NODE_ENV=production \
    PORT=3024 \
    CLOUD_BIND=0.0.0.0
EXPOSE 3024
# Liveness for orchestrators (compose/k8s) — the process is up when /v1/healthz answers.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3024/v1/healthz || exit 1
# Run the COMPILED entrypoint (no tsx in prod).
CMD ["node", "dist/index.js"]
