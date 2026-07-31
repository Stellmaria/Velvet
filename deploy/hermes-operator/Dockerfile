FROM python:3.13-alpine

RUN addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app app

WORKDIR /app
COPY deploy/hermes-operator/gateway.py /app/gateway.py

USER 10001:10001
ENTRYPOINT ["python", "/app/gateway.py"]
