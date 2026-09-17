# ---- Stage 1: Build React frontend ----
FROM node:20-alpine AS web-builder
WORKDIR /app/web
COPY apps/web/package.json ./
RUN npm install --legacy-peer-deps
COPY apps/web/ ./
RUN npm run build

# ---- Stage 2: Python API + static frontend ----
FROM python:3.12-slim
WORKDIR /app

# Install uv for fast installs
RUN pip install --no-cache-dir uv

# Copy Python project
COPY services/api/pyproject.toml ./
COPY services/api/src ./src
COPY contracts ./contracts

# Install dependencies
RUN uv pip install --system --no-cache -e .

# Copy built frontend into static/
COPY --from=web-builder /app/web/dist ./static

# Create work dir for local media (dev only; Cloud Run uses GCS)
RUN mkdir -p /app/work/media

# Environment
ENV PYTHONPATH=/app/src
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "kisanai_c2c.main:app", "--host", "0.0.0.0", "--port", "8080"]
