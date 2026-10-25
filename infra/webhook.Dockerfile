FROM node:22.16.0-alpine3.22
WORKDIR /gateway
COPY --chown=node:node infra/webhook-gateway.mjs ./webhook-gateway.mjs
USER node
ENV HOST=0.0.0.0 PORT=8010 API_UPSTREAM=http://api:8000
CMD ["node", "webhook-gateway.mjs"]
