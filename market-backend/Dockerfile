FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python --no-cache .
ENV PATH="/opt/venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
