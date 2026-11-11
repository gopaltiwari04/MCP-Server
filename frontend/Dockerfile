FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG ORCHESTRATOR_INTERNAL_URL=http://ai-orchestrator:8001
ENV ORCHESTRATOR_INTERNAL_URL=${ORCHESTRATOR_INTERNAL_URL}
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
