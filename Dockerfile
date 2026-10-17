FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==9.1.1
USER 65534:65534
WORKDIR /workspace
