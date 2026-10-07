"""Single researched horn request; transport evidence cannot prove sound."""

from collections.abc import Callable
from typing import Any

# WheelLog f44e39e5388e500a5d2f315d1dcf32f167607bf8 VeteranAdapter.
# One LkAp variant only; there is no established duration or stop command.
PACKET = bytes.fromhex("4c6b41700e0080808001ca87e66f")
FEEDBACK_SECONDS = 2.0


class HornRequests:
    def __init__(self, event: Callable[[dict[str, Any]], None]):
        self.event = event
        self.next_id = 1
        self.feedback: dict[str, Any] | None = None
        self.session: int | None = None
        self.pending: dict[int, int] = {}

    def show(self, message: str, now: float, session: int) -> None:
        self.session = session
        self.feedback = {"message": message, "expires_s": now + FEEDBACK_SECONDS}

    def request(self, now: float, session: int) -> dict[str, Any]:
        row = {"kind": "horn", "request": self.next_id, "session": session,
               "packet_hex": PACKET.hex(), "at_s": now}
        self.next_id += 1
        self.pending[row["request"]] = session
        if len(self.pending) > 32:
            del self.pending[next(iter(self.pending))]
        self.event({"event": "submission", **row})
        self.show("Horn request submitting", now, session)
        return row

    def result(self, request: int, session: int, success: bool, now: float, error: str = "") -> None:
        if self.pending.get(request) != session:
            return
        del self.pending[request]
        self.event({"event": "result", "kind": "horn", "request": request,
                    "session": session, "success": success, "at_s": now, "error": error})
        if request == self.next_id - 1:
            self.show("Horn request sent" if success else f"Horn request failed: {error or 'transport submission failed'}", now, session)

    def tick(self, now: float, session: int) -> None:
        if self.session != session:
            self.pending.clear()
        if self.feedback and (self.session != session or now >= self.feedback["expires_s"] - 1e-9):
            self.feedback = None
