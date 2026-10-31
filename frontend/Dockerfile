# syntax=docker/dockerfile:1.7
# Build stage: install locked dependencies and produce the static bundle.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runtime stage: unprivileged nginx serving static files; API paths are proxied to the back end.
FROM nginxinc/nginx-unprivileged:stable-alpine
# Pick up OS security fixes published after the base image was built (e.g. curl), then drop privileges.
USER root
RUN apk upgrade --no-cache
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
