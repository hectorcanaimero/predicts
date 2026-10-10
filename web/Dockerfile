# syntax=docker/dockerfile:1

# Build: Node 22, build de Vite estático en /app/dist.
FROM node:22-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runtime: nginx sirve el build y hace de proxy de /api (config montada desde
# deploy/nginx.conf vía docker-compose, ver deploy/docker-compose.yml).
FROM nginx:1.27-alpine AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
