FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip install --no-cache-dir "psycopg[binary]"
COPY . .
RUN mkdir -p /app/uploads && chmod +x /app/start.sh
EXPOSE 8000
CMD ["./start.sh"]
