# 1. Build the static site.
FROM node:24-alpine AS build
WORKDIR /app
# Dependencies first, so this layer stays cached when only the code changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# 2. Serve it. The "unprivileged" nginx image runs as a non-root user and listens on 8080.
FROM nginxinc/nginx-unprivileged:1-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
