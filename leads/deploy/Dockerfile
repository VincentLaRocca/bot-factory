# Inbound lead listener (+ optional sweep loop). Build from the repo root:
#   docker build -f leads/deploy/Dockerfile -t bot-factory-leads .
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY aiop aiop
COPY agents agents
COPY capabilities capabilities
COPY observer observer
COPY profiles profiles
COPY reasoning reasoning
COPY store store
COPY leads leads
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
# The store lives on a mounted volume at /data so dedupe survives redeploys.
CMD ["sh", "-c", "python -m leads --config ${LEADS_CONFIG:-leads/config.example.json} --store /data/leads.db loop --serve --every ${SWEEP_EVERY:-1800}"]
