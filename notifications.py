#!/usr/bin/env python3

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal
from dbus_next import RequestNameReply


if TYPE_CHECKING:
    import typing
    from dbus_next import Variant

    t_str = str
    t_uint32 = int
    t_int32 = int
    t_str_array = list[str]
    t_dict_str_variant = dict[str, Variant]
    t_str4 = list[str]
    t_uint32_str2 = list[int | str]
    t_uint32_2 = list[int]
    t_none: typing.TypeAlias = None
else:
    t_str = "s"
    t_uint32 = "u"
    t_int32 = "i"
    t_str_array = "as"
    t_dict_str_variant = "a{sv}"
    t_str4 = "ssss"
    t_uint32_str2 = "us"
    t_uint32_2 = "uu"
    t_none = ""


_DBUS_NAME = "org.freedesktop.Notifications"
_DBUS_PATH = "/org/freedesktop/Notifications"

CLOSE_REASON_EXPIRED = 1
CLOSE_REASON_DISMISSED = 2
CLOSE_REASON_CLOSED_BY_CALL = 3
CLOSE_REASON_UNDEFINED = 4
# Replacement maps to the spec reason for programmatic close.
CLOSE_REASON_REPLACED = CLOSE_REASON_CLOSED_BY_CALL


@dataclass(frozen=True)
class Notification:
    id: int
    replaces_id: int
    app_name: str
    app_icon: str
    summary: str
    body: str
    actions: list[str] = field(default_factory=list)
    hints: dict[str, Any] = field(default_factory=dict)
    expire_timeout: int = -1


class NotificationDaemon(ABC):
    """Abstract base class for a desktop notification daemon.

    Subclass this and implement `on_notify`. Override the other methods
    to customise behaviour. Pass an instance to `run_daemon` to start.
    """

    def __init__(self) -> None:
        self._emit_action: Callable[[int, str], None] = lambda _id, _key: None
        self._emit_closed: Callable[[int, int], None] = lambda _id, _reason: None

    def get_capabilities(self) -> list[str]:
        return ["body", "actions"]

    def get_server_information(self) -> tuple[str, str, str, str]:
        """Return (name, vendor, version, spec_version)."""
        return ("notify-daemon", "local", "0.2", "1.2")

    @abstractmethod
    def on_notify(self, notification: Notification) -> None:
        """Called when a notification is received."""
        ...

    def on_close_notification(self, id: int) -> None:
        """Called when a client requests that a notification be closed."""
        pass

    def _bind_signal_emitters(
        self,
        emit_action: Callable[[int, str], None],
        emit_closed: Callable[[int, int], None],
    ) -> None:
        self._emit_action = emit_action
        self._emit_closed = emit_closed

    def emit_action_invoked(self, notification_id: int, action_key: str) -> None:
        self._emit_action(notification_id, action_key)

    def emit_notification_closed(self, notification_id: int, reason: int) -> None:
        self._emit_closed(notification_id, reason)


class _DBusInterface(ServiceInterface):
    """Internal D-Bus service interface — wraps a NotificationDaemon."""

    def __init__(self, daemon: NotificationDaemon) -> None:
        super().__init__(_DBUS_NAME)
        self._daemon = daemon
        self._next_id = 1
        self._daemon._bind_signal_emitters(
            self._emit_action_invoked,
            self._emit_notification_closed,
        )

    @signal()
    def ActionInvoked(self, id: t_uint32, action_key: t_str) -> t_uint32_str2:
        return [id, action_key]

    @signal()
    def NotificationClosed(self, id: t_uint32, reason: t_uint32) -> t_uint32_2:
        return [id, reason]

    def _emit_action_invoked(self, notification_id: int, action_key: str) -> None:
        self.ActionInvoked(notification_id, action_key)

    def _emit_notification_closed(self, notification_id: int, reason: int) -> None:
        self.NotificationClosed(notification_id, reason)

    @method()
    def GetCapabilities(self) -> t_str_array:
        return self._daemon.get_capabilities()

    @method()
    def GetServerInformation(self) -> t_str4:
        return list(self._daemon.get_server_information())

    @method()
    def Notify(
        self,
        app_name: t_str,
        replaces_id: t_uint32,
        app_icon: t_str,
        summary: t_str,
        body: t_str,
        actions: t_str_array,
        hints: t_dict_str_variant,
        expire_timeout: t_int32,
    ) -> t_uint32:
        nid = self._next_id
        self._next_id += 1
        notification = Notification(
            id=nid,
            replaces_id=replaces_id,
            app_name=app_name,
            app_icon=app_icon,
            summary=summary,
            body=body,
            actions=list(actions),
            hints=dict(hints),
            expire_timeout=expire_timeout,
        )
        self._daemon.on_notify(notification)
        return nid

    @method()
    def CloseNotification(self, id: t_uint32) -> t_none:
        self._daemon.on_close_notification(id)
        self._emit_notification_closed(id, CLOSE_REASON_CLOSED_BY_CALL)


async def run_daemon(daemon: NotificationDaemon) -> None:
    """Connect to the session D-Bus, own the Notifications name, and run forever."""
    bus = await MessageBus().connect()

    reply = await bus.request_name(_DBUS_NAME)
    if reply != RequestNameReply.PRIMARY_OWNER:
        raise SystemExit(
            f"Failed to own {_DBUS_NAME}. "
            "Another notification daemon is already running."
        )

    bus.export(_DBUS_PATH, _DBusInterface(daemon))

    await asyncio.get_running_loop().create_future()  # run forever
