# The app needs two toolchains: Node to build the dashboard, Python to serve it
# and the API. Render's native Python runtime has no Node, so the build happens
# here instead — which also keeps the deployment portable to any host.

FROM node:20-slim AS frontend
WORKDIR /frontend
# Copy manifests first so `npm ci` is only re-run when dependencies change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Vite inlines VITE_* at build time from frontend/.env.production, which is
# committed because those values are public to the browser anyway.
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
# Backend deps only. The root requirements.txt also pulls in the collector's
# psutil, which this image never runs and which needs a compiler to build.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# main.py locates the dashboard at ../frontend/dist relative to itself, so the
# build output has to land in that same layout.
COPY --from=frontend /frontend/dist ./frontend/dist

WORKDIR /app/backend
# The host assigns the port; main.py reads PORT and falls back to 8000.
CMD ["python", "main.py"]
