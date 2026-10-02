FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY request_context.py .
COPY utils.py .
COPY middleware_google.py .
COPY oauth_google.py .
COPY main.py .
COPY tool_context.py .

EXPOSE 8080

CMD ["python", "main.py"]