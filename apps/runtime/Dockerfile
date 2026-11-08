# Build from the repo root: docker build -f apps/runtime/Dockerfile .
FROM node:26-bookworm-slim@sha256:bc0a2afd3b74ce12222fc8bab99271e66257f021078f5f4a5d687a77d280c1d9 AS build
RUN npm install -g pnpm@11.24.0
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile --filter @daftar/runtime... --filter @daftar/runtime-ui...
RUN pnpm --filter @daftar/spec build && pnpm --filter @daftar/runtime build && pnpm --filter @daftar/runtime-ui build
RUN pnpm --filter @daftar/runtime deploy --prod --legacy /out
# The operator's preview belongs to the Studio, never to a client's install (D-9). That goes for its source too,
# and nothing at runtime reads TypeScript.
RUN rm -f /out/dist/preview.js* /out/dist/preview-server.js* /out/dist/preview.d.ts* /out/dist/preview-server.d.ts*
RUN rm -rf /out/src /out/tsconfig.json /out/tsconfig.build.json
# Only the built page: the UI's sources and build tools stay out of a client's install.
RUN cp -r apps/runtime-ui/dist /out/ui

FROM node:26-bookworm-slim@sha256:bc0a2afd3b74ce12222fc8bab99271e66257f021078f5f4a5d687a77d280c1d9 AS runtime
WORKDIR /app
COPY --from=build /out .
USER node
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
    CMD node -e "fetch('http://127.0.0.1:3000/api/auth/status').then((r)=>process.exit(r.ok?0:1),()=>process.exit(1))"
CMD ["node", "dist/main.js"]
