# Dashboard — context/02 §3 e §6 (Bloco 7).
#
# Estágio 1: build estático do Vite. Estágio 2: nginx serve o build em HTTPS e
# faz proxy reverso de /api (REST e WebSocket) para o backend. Dashboard e API
# ficam na mesma origem, sem CORS. O certificado é autoassinado e gerado na
# primeira subida (docker-entrypoint.d/10-certificado.sh).

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
COPY nginx/dashboard.conf /etc/nginx/conf.d/default.conf
COPY nginx/10-certificado.sh /docker-entrypoint.d/10-certificado.sh
# Um clone com core.autocrlf=true (o padrão do Git no Windows) traria o script
# em CRLF, e o sh do Alpine não o rodaria.
RUN sed -i 's/\r$//' /docker-entrypoint.d/10-certificado.sh \
    && chmod +x /docker-entrypoint.d/10-certificado.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 443
