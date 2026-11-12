"""Controller lease: which browser may act on the laptop application, timed by a Clock."""

import asyncio
import secrets

from .clock import Clock
from .recording import Replay

# A side-button press with no browser activity for this long is released.
ABANDONED_PRESS_S = 2.0

# Application actions that end the live session before they run.
DISCONNECT_FIRST = ("simulator_start", "connect", "stop", "disconnect", "replay_start")

# Transport callbacks the application accepts only from its own adapters.
INTERNAL_ACTIONS = (
    "live_start",
    "live_connected",
    "live_disconnected",
    "command_result",
    "horn_result",
)


class ControllerExpired(Exception):
    """The browser's controller id no longer holds the lease."""


class Conflict(Exception):
    """The request cannot run against the current application state."""


class ControllerLease:
    def __init__(
        self,
        behavior,
        live,
        scenarios,
        clock: Clock,
        *,
        recorder=None,
        timeout=10.0,
        result_limit=2048,
    ):
        self.behavior = behavior
        self.live = live
        self.scenarios = scenarios
        self.clock = clock
        self.recorder = recorder
        self.timeout = timeout
        self.result_limit = result_limit
        self._results = {}
        self._seen = set()
        self._intent_lock = asyncio.Lock()
        self._controllers = set()
        self._documents: dict[str, str] = {}
        self._last_seen = self._now()

    def _now(self) -> float:
        return self.clock.read()[1]

    def expire(self) -> None:
        if self._controllers and self._now() - self._last_seen > self.timeout:
            self._cancel_preset_draft()
            self._controllers.clear()
            self._documents.clear()
            self._results.clear()
            self._seen.clear()
            if self.behavior.view()["button"]["down"]:
                self.behavior.action("button_up")

    def tick(self) -> None:
        self.expire()
        if (
            self._now() - self._last_seen > ABANDONED_PRESS_S
            and self.behavior.view()["button"]["down"]
        ):
            self.behavior.action("button_up")

    def _cancel_preset_draft(self) -> None:
        editor = self.behavior.view()["preset_editor"]
        if editor is not None:
            self.behavior.action("preset_cancel", editor_id=editor["id"])

    def observe(self, controller) -> None:
        """A state poll; it keeps the owner's lease alive and refuses an expired controller."""
        self.expire()
        if controller and controller not in self._controllers:
            raise ControllerExpired("Controller expired; reacquire current state")
        if controller in self._controllers:
            self._last_seen = self._now()

    def acquire(self, controller, document=None):
        """Return the browser's controller id, a new one, or None while another holds it."""
        self.expire()
        if controller not in self._controllers:
            if self._controllers:
                return None
            controller = secrets.token_urlsafe(16)
            self._controllers.add(controller)
        if document and len(document) <= 100:
            previous = self._documents.get(controller)
            if previous is not None and previous != document:
                self._cancel_preset_draft()
            self._documents[controller] = document
        self._last_seen = self._now()
        return controller

    def snapshot(self):
        return {
            **self.behavior.view(),
            "recording": None if self.recorder is None else self.recorder.status(),
            "live": self.live.status(),
            "scenario": self.scenarios.view(),
        }

    async def act(self, payload):
        """Run one browser request at most once and return the resulting snapshot."""
        self.expire()
        controller, identity = payload.pop("controller"), payload.pop("id")
        name = payload.pop("action")
        if not isinstance(name, str) or len(name) > 64:
            raise ValueError("Application action name required")
        if name in INTERNAL_ACTIONS:
            raise ValueError("Transport callbacks are internal application inputs")
        if (
            controller not in self._controllers
            or not isinstance(identity, str)
            or not identity
            or len(identity) > 128
        ):
            raise ValueError("Valid controller and request identity required")
        self._last_seen = self._now()
        key = (controller, identity)
        async with self._intent_lock:
            if controller not in self._controllers:
                raise ControllerExpired("Controller expired while action was waiting")
            if key in self._results:
                return self._results[key]
            if key in self._seen:
                raise Conflict("Duplicate action was already processed; its response expired")
            epoch = payload.pop("epoch", None)
            if type(epoch) is not int or epoch != self.behavior.session:
                raise Conflict("Application session changed; refresh before acting")
            await self._route(name, payload)
            result = self.snapshot()
            self._results[key] = result
            self._seen.add(key)
            if len(self._results) > self.result_limit:
                del self._results[next(iter(self._results))]
            return result

    async def _route(self, name, payload) -> None:
        behavior, live, scenarios = self.behavior, self.live, self.scenarios
        if name.startswith("scenario_"):
            if name == "scenario_save":
                scenarios.save_current(
                    behavior.simulator.values, payload.get("name"), payload.get("steps")
                )
            elif name == "scenario_review":
                scenarios.review(payload.get("content"))
            elif name == "scenario_export":
                scenarios.export()
            elif name == "scenario_start":
                scenarios.export()  # Validate a complete definition before disconnecting.
                await live.disconnect()
                scenarios.start(behavior)
            elif name == "scenario_step":
                scenarios.step(behavior)
            else:
                raise ValueError("Unknown scenario action")
        elif name == "live_discover":
            await live.discover()
        elif name == "live_select":
            await live.connect(payload["address"])
        elif name == "live_disconnect":
            await live.disconnect()
        else:
            if name in DISCONNECT_FIRST:
                await live.disconnect()
            if name == "replay_start":
                payload["recording"] = Replay.from_text(
                    payload["recording"], name=payload.pop("name", "Imported recording")
                )
            behavior.action(name, **payload)
