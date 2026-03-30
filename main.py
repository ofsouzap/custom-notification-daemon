#!/usr/bin/env python3

import asyncio
from typing import Final

import click

from notifications import Notification, NotificationDaemon, run_daemon
from renderer import BannerRenderer, ToastRenderer, NotificationRenderer


VERSION: Final[str] = "0.2.0"


class RendererNotificationDaemon(NotificationDaemon):
    def __init__(self, renderer: NotificationRenderer) -> None:
        super().__init__()
        self._renderer = renderer
        self._renderer.set_handlers(self._on_action, self._on_closed)

    def get_server_information(self) -> tuple[str, str, str, str]:
        return ("notify-gtk", "local", "0.1", "1.2")

    def on_notify(self, notification: Notification) -> None:
        self._renderer.show(notification)

    def on_close_notification(self, id: int) -> None:
        self._renderer.close(id)

    def _on_action(self, notification_id: int, action_key: str) -> None:
        self.emit_action_invoked(notification_id, action_key)

    def _on_closed(self, notification_id: int, reason: int) -> None:
        self.emit_notification_closed(notification_id, reason)


def _build_renderer(renderer_name: str) -> NotificationRenderer:
    if renderer_name == "toast":
        return ToastRenderer()
    if renderer_name == "banner":
        return BannerRenderer()

    raise click.ClickException(f"Unknown renderer: {renderer_name}")


def _run_daemon_with_renderer(renderer_name: str) -> None:
    click.echo(f"Starting custom-notification-daemon (renderer={renderer_name})")
    renderer = _build_renderer(renderer_name)
    asyncio.run(run_daemon(RendererNotificationDaemon(renderer)))


def _renderer_option(func: click.core.F) -> click.core.F:
    return click.option(
        "--renderer",
        "renderer_name",
        type=click.Choice(["toast", "banner"], case_sensitive=False),
        default="toast",
        show_default=True,
        help="Renderer backend to use.",
    )(func)


@click.version_option(version=VERSION, prog_name="custom-notification-daemon")
@click.group(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
def cli() -> None:
    """Custom notification daemon for Wayland/Sway."""
    pass


@cli.command("run")
@_renderer_option
def run_cmd(renderer_name: str) -> None:
    """Run the notifications daemon."""
    _run_daemon_with_renderer(renderer_name)


@cli.command("version")
def version_cmd() -> None:
    """Print daemon version."""
    click.echo(f"custom-notification-daemon {VERSION}")


if __name__ == "__main__":
    cli()
