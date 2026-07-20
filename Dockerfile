# Web app image. Runs the FastAPI dashboard bound to 0.0.0.0 so it's reachable
# from other devices on your LAN (e.g. your laptop's browser).
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "swgoh.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
