# apps/inference/core/bus/network.py
"""NetworkTransport — the bus spans two processes over a WebSocket.

The laptop runs a HubLink (WebSocket server); a satellite (Pi/ESP32/2nd process)
runs a SatelliteLink (WebSocket client). NetworkTransport implements the frozen
Transport ABC unchanged: send() delivers to LOCAL handlers inline (exactly like
InProcessTransport) AND ships the envelope to the peer; on receive the peer
dispatches to ITS local handlers. Layers never learn the difference.

The asyncio event loop runs in a daemon background thread started explicitly by
start() — never at import — so `core` stays import-safe with no live network.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from abc import abstractmethod
from collections import defaultdict
from typing import Any, Callable

from core.bus.transport import Handler, InProcessTransport, Transport
from core.protocol.decode import envelope_from_dict
from core.protocol.envelope import MessageEnvelope

logger = logging.getLogger(__name__)

_HEADER = "X-API-Key"
_QUEUE_MAXSIZE = 1000
_MAX_BACKOFF = 8.0
_READY_TIMEOUT = 5.0
_STOP_JOIN_TIMEOUT = 5.0

OnMessage = Callable[[str, MessageEnvelope], None]


class PeerLink:
    """One peer link: a background asyncio loop + a single WebSocket to the peer.

    Subclasses implement `_serve_or_connect` (server vs client). NetworkTransport
    wires `on_message` to its local transport so inbound frames dispatch to this
    node's handlers.
    """

    def __init__(self) -> None:
        self.on_message: OnMessage | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._stopping = False
        self._queue: asyncio.Queue[str] | None = None

    @property
    def peer_connected(self) -> bool:
        return False

    def start(self) -> None:
        """Spin up the background loop; idempotent. Never called at import.

        Raises the startup exception (e.g. bind failure) on the caller thread
        rather than returning a half-dead link whose network side silently died.
        """
        if self._thread is not None:
            return
        self._stopping = False
        self._ready.clear()
        self._start_error = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=_READY_TIMEOUT):
            self.stop()
            err = self._start_error
            raise RuntimeError(f"{type(self).__name__} failed to start within "
                               f"{_READY_TIMEOUT}s") from err
        if self._start_error is not None:
            err = self._start_error
            self.stop()
            raise RuntimeError(f"{type(self).__name__} failed to start") from err

    def _run_loop(self) -> None:
        loop = self._loop
        assert loop is not None
        asyncio.set_event_loop(loop)
        self._queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        try:
            loop.run_until_complete(self._serve_or_connect())
            loop.run_forever()
        except BaseException as exc:  # capture bind/serve failure for start()
            self._start_error = exc
            self._ready.set()  # unblock start() promptly so it can re-raise
        finally:
            loop.run_until_complete(self._drain_pending())
            loop.close()
            self._loop = None  # let stop()'s guard protect against the closed loop

    async def _drain_pending(self) -> None:
        pending = asyncio.all_tasks(self._loop) - {asyncio.current_task()}
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @abstractmethod
    async def _serve_or_connect(self) -> None:
        """Start the server (hub) or the connect/reconnect loop (satellite); set _ready."""

    def send_remote(self, topic: str, env: MessageEnvelope) -> None:
        """Enqueue a frame for the peer without blocking the caller (thread-safe)."""
        loop = self._loop  # snapshot: a concurrent stop() may null it under us
        if loop is None or self._stopping:
            return
        frame = json.dumps({"topic": topic, "env": env.to_dict()})
        try:
            loop.call_soon_threadsafe(self._enqueue, frame)
        except (RuntimeError, AttributeError):
            pass  # loop already closed / nulled between snapshot and call

    def _enqueue(self, frame: str) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()  # drop oldest
                self._queue.put_nowait(frame)
                logger.warning("peer link queue full — dropped oldest frame")
            except asyncio.QueueEmpty:
                pass

    def inject_raw_frame(self, frame: str) -> None:
        """Test aid: push a raw wire frame onto the outbound queue (no JSON guard)."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._enqueue, frame)

    async def _writer(self, ws: Any) -> None:
        # At-most-once across reconnect: a frame dequeued here is dropped (not
        # requeued) if the socket dies mid-send. Fine for continuously-resent
        # biometric streams; callers must not assume reliable last-frame delivery.
        assert self._queue is not None
        while True:
            frame = await self._queue.get()
            await ws.send(frame)

    async def _reader(self, ws: Any) -> None:
        async for message in ws:
            self._dispatch(message)

    def _dispatch(self, message: str) -> None:
        """Decode one inbound frame and hand it to local handlers; contain failures."""
        try:
            msg = json.loads(message)
            topic = msg["topic"]
            env = envelope_from_dict(msg["env"])
        except Exception:
            logger.warning("dropped malformed inbound frame")
            return
        if self.on_message is None:
            return
        try:
            self.on_message(topic, env)  # -> self._local.send -> sync handlers
        except Exception:
            logger.warning("inbound handler raised; contained")

    def stop(self) -> None:
        """Signal the loop to close and join the background thread."""
        self._stopping = True
        loop, thread = self._loop, self._thread
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._shutdown)
            except RuntimeError:
                pass  # loop already self-closed (e.g. failed start)
        if thread is not None:
            thread.join(timeout=_STOP_JOIN_TIMEOUT)
        self._loop = None
        self._thread = None
        self._queue = None

    @abstractmethod
    def _shutdown(self) -> None:
        """Close server/connection on the loop thread, then stop the loop."""

    def __enter__(self) -> "PeerLink":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()


class HubLink(PeerLink):
    """Laptop hub: a WebSocket server that accepts one authenticated satellite."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8787, *, key: str | None) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._key = key
        self._server: Any = None
        self._peer_ws: Any = None

    @property
    def peer_connected(self) -> bool:
        return self._peer_ws is not None

    async def _serve_or_connect(self) -> None:
        from websockets.asyncio.server import serve

        self._server = await serve(
            self._handler, self._host, self._port,
            process_request=self._process_request,
        )
        self._ready.set()

    def _process_request(self, connection: Any, request: Any) -> Any:
        """Reject the handshake unless X-API-Key matches; fail closed if unconfigured."""
        if not self._key:
            return connection.respond(503, "auth not configured\n")
        if request.headers.get(_HEADER) != self._key:
            return connection.respond(401, "invalid api key\n")
        return None

    async def _handler(self, ws: Any) -> None:
        self._peer_ws = ws
        writer = asyncio.ensure_future(self._writer(ws))
        try:
            await self._reader(ws)
        except Exception:
            logger.warning("hub peer connection closed")
        finally:
            writer.cancel()
            # Await teardown so a reconnecting satellite can't end up with two
            # writers draining the one shared queue onto different sockets.
            try:
                await writer
            except (asyncio.CancelledError, Exception):
                pass
            if self._peer_ws is ws:
                self._peer_ws = None

    def _shutdown(self) -> None:
        assert self._loop is not None
        asyncio.ensure_future(self._close_then_stop())

    async def _close_then_stop(self) -> None:
        ws, self._peer_ws = self._peer_ws, None
        if ws is not None:
            await ws.close()           # flush a clean close frame to the satellite
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        assert self._loop is not None
        self._loop.stop()


class SatelliteLink(PeerLink):
    """Satellite client: connects out to the hub, authenticates, reconnects on drop."""

    def __init__(self, uri: str, *, key: str | None) -> None:
        super().__init__()
        self._uri = uri
        self._key = key
        self._peer_ws: Any = None

    @property
    def peer_connected(self) -> bool:
        return self._peer_ws is not None

    async def _serve_or_connect(self) -> None:
        self._ready.set()
        asyncio.ensure_future(self._connect_loop())

    async def _connect_loop(self) -> None:
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus

        headers = {_HEADER: self._key} if self._key else {}
        backoff = 0.5
        while not self._stopping:
            try:
                async with connect(self._uri, additional_headers=headers,
                                   open_timeout=2.0) as ws:
                    self._peer_ws = ws
                    backoff = 0.5
                    writer = asyncio.ensure_future(self._writer(ws))
                    try:
                        await self._reader(ws)
                    finally:
                        writer.cancel()
                        self._peer_ws = None
            except InvalidStatus:
                logger.warning("satellite handshake rejected (auth)")
                return  # wrong key — do not hammer the hub
            except Exception:
                self._peer_ws = None
            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)

    def _shutdown(self) -> None:
        assert self._loop is not None
        asyncio.ensure_future(self._close_then_stop())

    async def _close_then_stop(self) -> None:
        ws, self._peer_ws = self._peer_ws, None
        if ws is not None:
            await ws.close()
        assert self._loop is not None
        self._loop.stop()


class NullLink(PeerLink):
    """No-op link: local delivery only (for the ABC-contract tests). No network."""

    def send_remote(self, topic: str, env: MessageEnvelope) -> None:
        return

    async def _serve_or_connect(self) -> None:
        self._ready.set()

    def _shutdown(self) -> None:
        if self._loop is not None:
            self._loop.stop()


class NetworkTransport(Transport):
    """Transport whose send() delivers locally inline AND forwards to one peer."""

    def __init__(self, link: PeerLink) -> None:
        self._local = InProcessTransport()
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._link = link
        link.on_message = self._dispatch_local

    def register(self, topic: str, handler: Handler) -> None:
        self._local.register(topic, handler)   # local send() keeps raise-through
        self._handlers[topic].append(handler)  # inbound dispatch (per-handler contained)

    def send(self, topic: str, env: MessageEnvelope) -> None:
        self._local.send(topic, env)          # (1) inline local delivery
        self._link.send_remote(topic, env)    # (2) enqueue to peer; non-blocking

    def _dispatch_local(self, topic: str, env: MessageEnvelope) -> None:
        """Inbound from the peer: dispatch to local handlers only — never re-forward.

        Per-handler containment (a raising handler must not starve the others, nor
        kill the loop) without touching the frozen InProcessTransport contract.
        """
        for handler in list(self._handlers.get(topic, [])):
            try:
                handler(env)
            except Exception:
                logger.warning("inbound handler raised; contained")
