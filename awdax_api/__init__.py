from awdax_api.routes import bp, register_websocket
from awdax_api import ask_routes, key_routes, mcp_proxy, openapi  # noqa: F401  (add their routes to bp before it is registered)
from awdax_api.live_bridge import live_bridge


def init_awdax_api(app) -> None:
    from auth_helper import AuthError
    from awdax_api.errors import detail_response

    app.register_error_handler(AuthError, lambda exc: detail_response(401, str(exc)))
    app.register_blueprint(bp)
    live_bridge.start()
    try:
        from flask_sock import Sock

        sock = Sock(app)
        register_websocket(sock)
    except ImportError:
        app.logger.warning("flask-sock not installed; WebSocket live stream disabled (SSE still works)")
