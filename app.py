import logging
import os
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

from awdax_api import init_awdax_api  # noqa: E402
from awdax_api.errors import detail_response  # noqa: E402

app = Flask(__name__)
init_awdax_api(app)


@app.errorhandler(404)
def _not_found(_error):
    # Only the React API exists (/api/instances*, /health, /ready). Every other path, including the retired
    # pre-React routes, gets the same JSON 404 the API uses.
    return detail_response(404, "Not found")


if __name__ == "__main__":
    from awdax_api.orchestrator import recover_interrupted_runs

    # No run thread exists yet, so a session still marked running was cut off by the last restart.
    recover_interrupted_runs()
    port = int(os.getenv("PORT", "8000"))
    # The Werkzeug debugger must never face the tunnel; FLASK_DEBUG=1 turns it on for local debugging only.
    app.run(host="127.0.0.1", port=port, debug=os.getenv("FLASK_DEBUG") == "1", use_reloader=False, threaded=True)
