# The AWDAX backend: Flask under gunicorn, with Chromium for the pages that need a browser.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    SQLITE_PATH=/data/regulatory.sqlite \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY *.py ./
COPY awdax_api ./awdax_api
COPY mcp_server ./mcp_server
COPY deploy/gunicorn.conf.py ./deploy/gunicorn.conf.py

# Not root: the database lives on the /data volume.
RUN useradd --create-home --uid 10001 awdax && mkdir -p /data && chown awdax /data
USER awdax
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "app:app"]
