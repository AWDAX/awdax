"""gunicorn settings for the AWDAX backend (see docs/DEPLOY.md).

One worker on purpose: the run limits, the waiting line, the live loops and the event bridge live in this process's memory, so a second
worker would split them. Concurrency comes from threads (runs, the live stream and WebSockets each hold one).
"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = 1
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "64"))
timeout = 120  # a worker is only restarted if its main thread stops answering for this long; streams are not affected
graceful_timeout = 30
accesslog = "-"
errorlog = "-"


def post_worker_init(worker):
    from app import startup

    startup()
