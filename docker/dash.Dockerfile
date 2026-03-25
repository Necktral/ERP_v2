FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY dash_analytics/requirements.txt /tmp/dash-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dash-requirements.txt

COPY dash_analytics /app/dash_analytics

EXPOSE 8050

CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4", "dash_analytics.app:server"]
