FROM python:3.13-alpine

RUN addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app app

WORKDIR /app
COPY --chmod=0555 deploy/hermes-operator/gateway.py /app/gateway.py
COPY --chmod=0555 deploy/hermes-operator/coder_router.py /app/coder_router.py
COPY --chmod=0555 deploy/hermes-operator/tier_router.py /app/tier_router.py
COPY --chmod=0555 deploy/hermes-operator/codex_image_router.py /app/codex_image_router.py
COPY --chmod=0555 deploy/hermes-operator/evidence_router.py /app/evidence_router.py

USER 10001:10001
CMD ["python", "/app/gateway.py"]
