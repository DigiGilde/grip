FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginxinc/nginx-unprivileged:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

# The image's entrypoint runs envsubst over this template at start and writes
# the result to /etc/nginx/nginx.conf. Only BACKEND_URL is substituted, so
# nginx's own $variables survive.
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx \
    NGINX_ENVSUBST_FILTER=BACKEND_URL \
    BACKEND_URL=http://backend:8080

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
