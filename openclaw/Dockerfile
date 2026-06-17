ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest
FROM ${OPENCLAW_IMAGE}

USER root
RUN mkdir -p /home/node/.openclaw && chown -R node:node /home/node/.openclaw
USER node

COPY --chown=node:node openclaw.json5 /home/node/.openclaw/openclaw.json
COPY --chown=node:node agents /home/node/.openclaw/agents
COPY --chown=node:node skills /home/node/.openclaw/skills
