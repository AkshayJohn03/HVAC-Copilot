# Minimal runtime image for the HVAC-Copilot service (used by PlatformDemo's docker-compose).
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY corpus ./corpus
RUN pip install --no-cache-dir .
CMD ["uvicorn", "hvac_copilot.serve.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8300"]
