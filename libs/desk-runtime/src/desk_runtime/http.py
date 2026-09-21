from bottle import request, response

from desk_runtime.serialization import to_json


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


def json_error(message, status, **fields):
    return json_response({"error": message, **fields}, status)


def query_text(name, default=None):
    value = (request.query.get(name) or "").strip()
    return value or default


def query_upper(name, default=None):
    value = query_text(name)
    return value.upper() if value is not None else default


def query_flag(name):
    return query_text(name, "") in ("1", "true")


def install_json_errors(app):
    def render(error):
        response.content_type = "application/json"
        return to_json({"error": str(error.body or error.status_line)})

    app.default_error_handler = render
