FROM python:3.13-alpine

RUN addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app app

WORKDIR /app
COPY --chmod=0555 deploy/hermes-operator/gateway.py /app/gateway.py
COPY --chmod=0555 deploy/hermes-operator/coder_router.py /app/coder_router.py

USER 10001:10001
CMD ["python", "/app/gateway.py"]
