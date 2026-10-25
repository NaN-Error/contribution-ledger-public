FROM node:22.16.0-bookworm-slim AS build
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
# The gateway tests import this trusted source using its monorepo-relative path.
COPY infra/webhook-gateway.mjs /repo/infra/webhook-gateway.mjs
RUN npm test && npm run build

FROM build AS test
CMD ["npm", "test"]

FROM node:22.16.0-bookworm-slim AS runtime
ENV NODE_ENV=production CL_BIND_HOST=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/web/dist ./dist
COPY --from=build --chown=node:node /repo/apps/web/server.mjs ./server.mjs
USER node
CMD ["node", "server.mjs"]
