FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginxinc/nginx-unprivileged:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

# The image's entrypoint runs envsubst over this template at start and writes
# the result to /etc/nginx/nginx.conf. No variable is substituted (the filter
# matches nothing), so nginx's own $variables survive.
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
# Writes the /api/ part of the configuration from BACKEND_URL, at start.
COPY --chmod=755 docker-api-proxy.sh /docker-entrypoint.d/05-grip-api.sh
# BACKEND_URL is empty by default: set it to the backend as this container
# reaches it (for example http://backend:8080), or leave it empty when the
# platform sends /api/ to the backend itself. SECURITY_TXT_URL is the
# security.txt of the organisation that runs the instance.
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx \
    NGINX_ENVSUBST_FILTER=GRIP_NOTHING_TO_SUBSTITUTE \
    BACKEND_URL="" \
    SECURITY_TXT_URL=""

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
