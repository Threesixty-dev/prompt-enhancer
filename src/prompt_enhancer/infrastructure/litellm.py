"""Bounded HTTPS chat adapter; credentials and text are never logged here."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import ssl
import socket
import threading
from urllib.parse import urlsplit

from ..config import LiteLLMSettings
from ..application.inference import InferenceModel, InferenceStream, InferenceTransportError
from ..application.runtime_cancellation import (
    current_runtime_cancellation, raise_if_runtime_cancelled,
)

LITELLM_ADAPTER_VERSION = "litellm-chat-v1"
MAX_RESPONSE_BYTES = 256_000
MAX_STREAM_BYTES = 16 * 1024 * 1024
MAX_STREAM_LINE_BYTES = 256_000


class _PrivateHTTPSConnection(http.client.HTTPSConnection):
    """Dial a configured cluster address while verifying the URL's TLS name."""

    def __init__(self, host, port, *, address, context, timeout):
        super().__init__(host, port, context=context, timeout=timeout)
        self._address = address
        self._verified_context = context

    def connect(self):
        raw = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._verified_context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class LiteLLMChat:
    _path = "/v1/chat/completions"

    def __init__(self, settings: LiteLLMSettings, *, expected_route_id: str | None = None,
                 report_failures: bool = False) -> None:
        self._settings = settings
        self._expected_route_id = expected_route_id
        self._report_failures = report_failures

    def __call__(self, alias: str, body: bytes) -> tuple[int, bytes, str]:
        reply = self._request(alias, body, stream=False)
        return reply.status_code, reply.body or b"{}", reply.content_type

    def open_chat(self, alias: str, body: bytes) -> InferenceStream:
        return self._request(alias, body, stream=True)

    def _failure(self, code: str) -> InferenceStream:
        if self._report_failures:
            raise InferenceTransportError(code) from None
        return InferenceStream(502, "application/json", b"{}")

    def _prepare_payload(self, payload: dict, *, stream: bool) -> dict | None:
        if not isinstance(payload.get("messages"), list):
            return None
        payload.pop("chat_template_kwargs", None)
        if self._settings.reasoning_effort is not None:
            payload["reasoning_effort"] = self._settings.reasoning_effort
        payload.update({"model": self._settings.model, "stream": stream, "no-log": True})
        if not stream:
            payload.pop("stream_options", None)
        return payload

    def _request(self, alias: str, body: bytes, *, stream: bool) -> InferenceStream:
        config = self._settings
        if alias != config.model:
            return self._failure("gateway_request_invalid")
        raise_if_runtime_cancelled()
        try:
            if len(body) > MAX_STREAM_BYTES:
                return self._failure("gateway_request_invalid")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                return self._failure("gateway_request_invalid")
            payload = self._prepare_payload(payload, stream=stream)
            if payload is None:
                return self._failure("gateway_request_invalid")
        except (ValueError, TypeError):
            return self._failure("gateway_request_invalid")
        url = urlsplit(config.base_url)
        context = ssl.create_default_context()
        pin = None
        if config.tls_cert_pem is not None:
            pem = config.tls_cert_pem.get_secret_value()
            context = ssl.create_default_context(cadata=pem)
            # Validate the chain, expiry, hostname AND exact leaf before auth.
            pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).digest()
        if config.connect_address is not None:
            connection = _PrivateHTTPSConnection(
                url.hostname, url.port or 443, address=config.connect_address,
                context=context, timeout=5,
            )
        else:
            connection = http.client.HTTPSConnection(
                url.hostname, url.port or 443, context=context, timeout=5,
            )
        finished = threading.Event()
        cancellation = current_runtime_cancellation()
        retained = False
        active_socket = None
        connected = False

        def cancel():
            finished.set()
            # HTTPConnection can release its socket reference after headers
            # (Connection: close), while HTTPResponse still owns a blocking
            # file reader. Retain the socket so Stop can interrupt that reader.
            sock = connection.sock or active_socket
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except (OSError, AttributeError):
                    pass
            connection.close()

        def watch():
            while not finished.wait(.05):
                if cancellation is not None and cancellation.is_set():
                    cancel()
                    return

        watcher = threading.Thread(target=watch, name="inference-cancellation", daemon=True) if cancellation is not None else None
        if watcher is not None:
            watcher.start()

        def finish():
            cancel()
            if watcher is not None and watcher is not threading.current_thread():
                watcher.join(timeout=1)

        try:
            connection.connect()
            connected = True
            active_socket = connection.sock
            raise_if_runtime_cancelled()
            if hasattr(connection.sock, "settimeout"):
                connection.sock.settimeout(90)
            assert connection.sock is not None
            if pin is not None:
                actual = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()
                if not hmac.compare_digest(pin, actual):
                    return self._failure("gateway_tls_failed")
            headers = {
                "Host": url.netloc,
                "User-Agent": "prompt-enhancer-bench/1.0",
                "Authorization": "Bearer " + config.credential.get_secret_value(),
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "x-litellm-enable-message-redaction": "true",
            }
            if config.access_client_id is not None and config.access_client_secret is not None:
                headers["CF-Access-Client-Id"] = config.access_client_id.get_secret_value()
                headers["CF-Access-Client-Secret"] = config.access_client_secret.get_secret_value()
            connection.request("POST", self._path, json.dumps(payload).encode(), headers)
            response = connection.getresponse()
            # Never follow redirects or propagate gateway errors/headers.
            if response.status != 200:
                code = {401: "gateway_http_unauthorized", 403: "gateway_http_forbidden",
                        429: "gateway_http_rate_limited"}.get(response.status)
                if code is None:
                    code = ("gateway_http_redirect" if 300 <= response.status < 400 else
                            "gateway_http_client_error" if 400 <= response.status < 500 else
                            "gateway_http_server_error" if 500 <= response.status < 600 else
                            "gateway_http_unexpected_status")
                return self._failure(code)
            if self._expected_route_id is not None and (
                not hasattr(response, "getheader")
                or response.getheader("x-litellm-model-id") != self._expected_route_id
            ):
                return self._failure("gateway_route_mismatch")
            content_type = response.getheader("Content-Type", "application/json") if hasattr(response, "getheader") else "application/json"
            if stream and "text/event-stream" in content_type:
                def lines():
                    size = 0
                    try:
                        while True:
                            raise_if_runtime_cancelled()
                            line = response.readline(MAX_STREAM_LINE_BYTES + 1)
                            if not line:
                                break
                            size += len(line)
                            if len(line) > MAX_STREAM_LINE_BYTES or size > MAX_STREAM_BYTES:
                                raise OSError("inference_response_too_large")
                            yield line
                    except (OSError, ValueError, http.client.HTTPException):
                        raise_if_runtime_cancelled()
                        raise OSError("inference_stream_failed") from None
                    finally:
                        finish()
                retained = True
                return InferenceStream(200, "text/event-stream", lines=lines(), cancel=finish)
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                return self._failure("gateway_response_too_large")
            raise_if_runtime_cancelled()
            return InferenceStream(200, "application/json", data)
        except ssl.SSLError:
            raise_if_runtime_cancelled()
            return self._failure("gateway_tls_failed")
        except TimeoutError:
            raise_if_runtime_cancelled()
            return self._failure("gateway_io_timeout" if connected else "gateway_connect_timeout")
        except OSError:
            raise_if_runtime_cancelled()
            return self._failure("gateway_io_failed" if connected else "gateway_connect_failed")
        except (ValueError, http.client.HTTPException):
            raise_if_runtime_cancelled()
            return self._failure("gateway_protocol_error")
        finally:
            if not retained:
                finish()


class LiteLLMEmbedding(LiteLLMChat):
    """Two explicit texts over the same bounded, cancellable TLS transport."""

    _path = "/v1/embeddings"

    def _prepare_payload(self, payload: dict, *, stream: bool) -> dict | None:
        inputs = payload.get("input")
        if (stream or set(payload) != {"input"} or not isinstance(inputs, list)
                or len(inputs) != 2
                or any(not isinstance(text, str) or not 1 <= len(text) <= 20_000 for text in inputs)):
            return None
        return {"model": self._settings.model, "input": inputs,
                "encoding_format": "float", "truncate": False, "no-log": True}


class LiteLLMNli(LiteLLMChat):
    """Three-way paired-text classification through Xinference's native API."""

    _path = "/v1/bench/nli"

    def _prepare_payload(self, payload: dict, *, stream: bool) -> dict | None:
        if (stream or set(payload) != {"premise", "hypothesis", "model_revision"}
                or any(not isinstance(payload.get(key), str) or not 1 <= len(payload[key]) <= 20_000
                       for key in ("premise", "hypothesis"))
                or payload.get("model_revision") != self._settings.model_revision):
            return None
        return {"model": self._settings.model,
                "args": [{"text": payload["premise"], "text_pair": payload["hypothesis"]}],
                "top_k": None, "truncation": False}


class LiteLLMRerank(LiteLLMChat):
    """One explicit query/document pair; no provider or endpoint overrides."""

    _path = "/v1/rerank"

    def _prepare_payload(self, payload: dict, *, stream: bool) -> dict | None:
        if (stream or set(payload) != {"query", "document"}
                or any(not isinstance(payload.get(key), str) or not 1 <= len(payload[key]) <= 20_000
                       for key in ("query", "document"))):
            return None
        return {"model": self._settings.model, "query": payload["query"],
                "documents": [payload["document"]], "top_n": 1,
                "return_documents": False, "no-log": True}


class LiteLLMProvider:
    """External model adapter; no registry files, process handles or GPU claims."""
    provider_id = "litellm"
    def __init__(self, settings: LiteLLMSettings, transport: LiteLLMChat | None = None):
        self._settings = settings
        self._transport = transport or LiteLLMChat(settings)
        self.model_id = "gateway-" + hashlib.sha256(settings.model.encode()).hexdigest()[:16]

    def models(self) -> tuple[InferenceModel, ...]:
        return (InferenceModel(id=self.model_id, name=self._settings.model,
            provider="litellm", remote=True, available=True, availability="configured",
            revision=self._settings.model_revision, license=self._settings.model_license,
            adapter_version="litellm-inference.v1"),)

    def complete(self, model_id: str, body: bytes) -> tuple[int, bytes, str]:
        if model_id != self.model_id:
            return 502, b"{}", "application/json"
        return self._transport(self._settings.model, body)

    def open_chat(self, model_id: str, body: bytes) -> InferenceStream:
        if model_id != self.model_id:
            return InferenceStream(502, "application/json", b"{}")
        return self._transport.open_chat(self._settings.model, body)
