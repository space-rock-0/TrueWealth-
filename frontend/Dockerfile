# Build stage
FROM node:20-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# Nginx expands API_PROXY_HOST at container startup. This keeps API keys and
# provider headers on the browser-to-app request path without baking a URL in.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV API_PROXY_HOST=backend:5001
ENV NGINX_ENVSUBST_FILTER=^API_PROXY_HOST$

# Copy custom nginx config if needs to handle client-side routing
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
