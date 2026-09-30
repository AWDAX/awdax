from awdax_api.routes import bp, register_websocket
from awdax_api.live_bridge import live_bridge


def init_awdax_api(app) -> None:
    app.register_blueprint(bp)
    live_bridge.start()
    try:
        from flask_sock import Sock

        sock = Sock(app)
        register_websocket(sock)
    except ImportError:
        app.logger.warning("flask-sock not installed; WebSocket live stream disabled (SSE still works)")
