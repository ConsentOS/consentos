# Build context is the repo root so we can see apps/banner/ alongside
# apps/admin-ui/. A .dockerignore at the repo root keeps this cheap.

# ── Stage 1: build the banner bundle ────────────────────────────────
FROM node:20-slim AS banner-builder
WORKDIR /build/banner
COPY apps/banner/package.json apps/banner/package-lock.json ./
RUN npm ci
COPY apps/banner/ .
RUN npm run build

# ── Stage 2: build the admin UI ─────────────────────────────────────
FROM node:20-slim AS admin-builder
WORKDIR /build/admin
COPY apps/admin-ui/package.json apps/admin-ui/package-lock.json ./
RUN npm ci
COPY apps/admin-ui/ .
# Drop the banner build output at the web root so it's served as
# /consent-loader.js and /consent-bundle.js. The loader resolves the
# bundle URL from its own origin (see apps/banner/src/loader.ts), so
# both files must live at the origin root — not under a sub-path.
COPY --from=banner-builder /build/banner/dist/ ./public/
RUN npx vite build

# ── Stage 3: serve with nginx ───────────────────────────────────────
FROM nginx:alpine
COPY --from=admin-builder /build/admin/dist /usr/share/nginx/html
COPY apps/admin-ui/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
