#!/bin/sh
# Certificado autoassinado do dashboard (context/02 §6: "nginx + certificado
# autoassinado em dev"). Gerado uma vez, no volume, para o navegador não pedir
# uma exceção nova a cada `docker compose up`. Apagar o volume gera outro.
set -eu

DIR=/etc/nginx/certs
if [ -s "$DIR/certificado.pem" ] && [ -s "$DIR/chave.pem" ]; then
    exit 0
fi

mkdir -p "$DIR"
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$DIR/chave.pem" -out "$DIR/certificado.pem" \
    -subj "/CN=localhost/O=TCC UNIP 2026 - somente desenvolvimento" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
chmod 600 "$DIR/chave.pem"
echo "10-certificado.sh: certificado autoassinado gerado em $DIR"
