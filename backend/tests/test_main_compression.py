"""Responses are gzip-compressed for clients that accept it, except event streams."""

from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from fastapi.testclient import TestClient

import main

MODEL = b"glTF" + bytes(4000)


def _client_with_main_middleware() -> TestClient:
    app = FastAPI()
    app.user_middleware.extend(main.app.user_middleware)

    @app.get("/model")
    def model():
        return Response(MODEL, media_type="model/gltf-binary")

    @app.get("/events")
    def events():
        return StreamingResponse(iter([b"data: 1\n\n" * 400]), media_type="text/event-stream")

    return TestClient(app)


def test_models_are_compressed_for_clients_that_accept_gzip():
    client = _client_with_main_middleware()

    compressed = client.get("/model", headers={"Accept-Encoding": "gzip"})
    assert compressed.headers["content-encoding"] == "gzip"
    assert int(compressed.headers["content-length"]) < len(MODEL) // 10
    assert compressed.content == MODEL  # decoded by the client

    plain = client.get("/model", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert plain.content == MODEL


def test_event_streams_are_never_compressed():
    events = _client_with_main_middleware().get(
        "/events", headers={"Accept-Encoding": "gzip"}
    )
    assert "content-encoding" not in events.headers
