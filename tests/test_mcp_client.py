import threading
from types import SimpleNamespace

from mao_cli import mcp_client
from mao_cli.registry import MCPServerRecord


def test_mcp_session_pool_reuses_one_portal_thread(monkeypatch) -> None:
    tracker: dict[str, list[int] | list[bool]] = {
        "transport_enter": [],
        "transport_exit": [],
        "transport_exit_matches": [],
        "session_enter": [],
        "session_exit": [],
        "session_exit_matches": [],
        "initialize_threads": [],
        "initialize_matches": [],
        "call_threads": [],
        "call_matches": [],
    }

    class FakeTransportCM:
        def __init__(self) -> None:
            self.enter_thread = -1

        async def __aenter__(self):
            self.enter_thread = threading.get_ident()
            tracker["transport_enter"].append(self.enter_thread)
            return object(), object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            exit_thread = threading.get_ident()
            tracker["transport_exit"].append(exit_thread)
            tracker["transport_exit_matches"].append(exit_thread == self.enter_thread)

    class FakeSession:
        def __init__(self, owner_thread: int) -> None:
            self.owner_thread = owner_thread

        async def initialize(self) -> None:
            current = threading.get_ident()
            tracker["initialize_threads"].append(current)
            tracker["initialize_matches"].append(current == self.owner_thread)

        async def call_tool(self, tool: str, arguments=None):
            current = threading.get_ident()
            tracker["call_threads"].append(current)
            tracker["call_matches"].append(current == self.owner_thread)
            suffix = arguments.get("n") if isinstance(arguments, dict) else ""
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=f"{tool}:{suffix}")],
                structuredContent=None,
            )

    class FakeSessionCM:
        def __init__(self) -> None:
            self.enter_thread = -1

        async def __aenter__(self):
            self.enter_thread = threading.get_ident()
            tracker["session_enter"].append(self.enter_thread)
            return FakeSession(self.enter_thread)

        async def __aexit__(self, exc_type, exc, tb) -> None:
            exit_thread = threading.get_ident()
            tracker["session_exit"].append(exit_thread)
            tracker["session_exit_matches"].append(exit_thread == self.enter_thread)

    monkeypatch.setattr(mcp_client, "_stdio_transport_cm", lambda server: FakeTransportCM())
    monkeypatch.setattr(mcp_client, "_client_session_cm", lambda read_stream, write_stream: FakeSessionCM())

    record = MCPServerRecord(name="fake", transport="stdio", command="python")

    with mcp_client.MCPSessionPool.open() as pool:
        first = pool.call_tool(record, tool="ping", arguments={"n": 1})
        second = pool.call_tool(record, tool="pong", arguments={"n": 2})

    assert first.text == "ping:1"
    assert second.text == "pong:2"
    assert len(tracker["transport_enter"]) == 1
    assert len(tracker["session_enter"]) == 1
    assert tracker["initialize_matches"] == [True]
    assert tracker["call_matches"] == [True, True]
    assert tracker["transport_exit_matches"] == [True]
    assert tracker["session_exit_matches"] == [True]
