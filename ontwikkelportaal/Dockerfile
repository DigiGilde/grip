# Build context: the repository root (docker build -f ontwikkelportaal/Dockerfile .).
# The .dockerignore there lets only ontwikkelportaal/ and docs/ through.
# glibc base: the Pagefind and Rolldown binaries in the lockfile are the gnu builds.
FROM node:22-bookworm-slim AS builder

WORKDIR /src/ontwikkelportaal
COPY ontwikkelportaal/package.json ontwikkelportaal/package-lock.json ./
# No install scripts: the build needs none, and a hijacked release cannot run its hooks here.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY ontwikkelportaal/ ./
# The site reads its Markdown from ../docs, as in the repository.
COPY docs /src/docs
# Builds the site and its Pagefind index, then checks links, scripts and navigation.
RUN npm run build && npm run check


FROM nginxinc/nginx-unprivileged:alpine AS production

COPY --from=builder /src/ontwikkelportaal/dist /usr/share/nginx/html

# The image's entrypoint runs envsubst over this template at start and writes
# the result to /etc/nginx/nginx.conf. No variable is substituted (the filter
# matches nothing), so nginx's own $variables survive.
COPY ontwikkelportaal/nginx.conf.template /etc/nginx/templates/nginx.conf.template
# Writes the config.json that the start page fetches.
COPY --chmod=755 ontwikkelportaal/write-config.sh /docker-entrypoint.d/05-ontwikkelportaal-config.sh
# ONTWIKKELPORTAAL_INSTANCES is a JSON list of {"naam", "rol", "omschrijving",
# "url"}; see docs/uitrol-zad.md.
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx \
    NGINX_ENVSUBST_FILTER=GRIP_NOTHING_TO_SUBSTITUTE \
    ONTWIKKELPORTAAL_INSTANCES="[]"

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
