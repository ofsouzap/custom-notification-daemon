#!/usr/bin/env python3

import sys
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from notifications import (
    CLOSE_REASON_DISMISSED,
    CLOSE_REASON_EXPIRED,
    CLOSE_REASON_REPLACED,
    CLOSE_REASON_UNDEFINED,
    Notification,
)


class NotificationRenderer(ABC):
    """Receives Notification objects and presents them to the user."""

    @abstractmethod
    def show(self, notification: Notification) -> None:
        """Display the given notification."""
        ...

    def close(self, notification_id: int) -> None:
        """Close a currently displayed notification by its ID."""
        pass

    def set_handlers(
        self,
        on_action: Callable[[int, str], None],
        on_closed: Callable[[int, int], None],
    ) -> None:
        """Set callbacks for user actions and close events."""
        pass


class _BaseGtkRenderer(NotificationRenderer):
    _DEFAULT_TIMEOUT_MS = 5000

    def __init__(self) -> None:
        import gi

        gtk_major = 3
        try:
            gi.require_version("Gtk", "3.0")
        except ValueError:
            gi.require_version("Gtk", "4.0")
            gtk_major = 4

        from gi.repository import Gtk, Gdk, GLib

        layer_shell = None
        if gtk_major == 3:
            for version in ("0.1", "0"):
                try:
                    gi.require_version("GtkLayerShell", version)
                    from gi.repository import GtkLayerShell

                    layer_shell = GtkLayerShell
                    break
                except ValueError:
                    continue
        else:
            for version in ("1.0", "0"):
                try:
                    gi.require_version("Gtk4LayerShell", version)
                    from gi.repository import Gtk4LayerShell

                    layer_shell = Gtk4LayerShell
                    break
                except ValueError:
                    continue

        self._Gtk = Gtk
        self._Gdk = Gdk
        self._GLib = GLib
        self._gtk_major = gtk_major
        self._GtkLayerShell = layer_shell
        self._main_loop = None

        if self._GtkLayerShell is None:
            print(
                "[custom-notification-daemon] Running without GtkLayerShell. "
                "Notifications will be regular windows. "
                "Install: gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 "
                "libgtk-layer-shell0",
                file=sys.stderr,
            )

        self._windows: dict[int, Any] = {}
        self._lock = threading.Lock()
        self._on_action: Callable[[int, str], None] = lambda _id, _key: None
        self._on_closed: Callable[[int, int], None] = lambda _id, _reason: None
        self._timeout_sources: dict[int, int] = {}

        if self._gtk_major == 3:
            gtk_thread = threading.Thread(target=Gtk.main, daemon=True)
        else:
            self._main_loop = GLib.MainLoop()
            gtk_thread = threading.Thread(target=self._main_loop.run, daemon=True)
        gtk_thread.start()

    def show(self, notification: Notification) -> None:
        self._GLib.idle_add(self._create_window, notification)

    @abstractmethod
    def _create_window(self, notification: Notification) -> bool:
        """Create and show renderer-specific UI for a notification."""
        ...

    def close(self, notification_id: int) -> None:
        self._GLib.idle_add(
            self._destroy_window,
            notification_id,
            False,
            CLOSE_REASON_DISMISSED,
        )

    def set_handlers(
        self,
        on_action: Callable[[int, str], None],
        on_closed: Callable[[int, int], None],
    ) -> None:
        self._on_action = on_action
        self._on_closed = on_closed

    def _destroy_window(
        self,
        notification_id: int,
        emit_closed: bool = False,
        close_reason: int = CLOSE_REASON_UNDEFINED,
    ) -> bool:
        with self._lock:
            win = self._windows.pop(notification_id, None)
            timeout_source = self._timeout_sources.pop(notification_id, None)

        if win is not None:
            if timeout_source is not None:
                self._GLib.source_remove(timeout_source)
            win.destroy()
            if emit_closed:
                self._on_closed(notification_id, close_reason)

        return False

    def _bind_click_to_dismiss(self, widget: Any, notification_id: int) -> None:
        if self._gtk_major == 3:
            if hasattr(widget, "add_events") and hasattr(self._Gdk, "EventMask"):
                widget.add_events(self._Gdk.EventMask.BUTTON_PRESS_MASK)
            widget.connect(
                "button-press-event",
                self._on_notification_clicked_gtk3,
                notification_id,
            )
            return

        if (
            self._gtk_major == 4
            and hasattr(self._Gtk, "GestureClick")
            and hasattr(widget, "add_controller")
        ):
            click = self._Gtk.GestureClick()
            click.set_button(1)
            click.connect(
                "pressed",
                self._on_notification_clicked_gtk4,
                notification_id,
            )
            widget.add_controller(click)

    def _on_notification_clicked_gtk3(
        self,
        _widget: object,
        _event: object,
        notification_id: int,
    ) -> bool:
        self._destroy_window(notification_id, True, CLOSE_REASON_DISMISSED)
        return False

    def _on_notification_clicked_gtk4(
        self,
        _gesture: object,
        _n_press: int,
        _x: float,
        _y: float,
        notification_id: int,
    ) -> None:
        self._destroy_window(notification_id, True, CLOSE_REASON_DISMISSED)

    def _on_action_clicked(
        self, _button: object, notification_id: int, action_key: str
    ) -> None:
        self._on_action(notification_id, action_key)
        self._destroy_window(notification_id, True, CLOSE_REASON_DISMISSED)

    @staticmethod
    def _parse_actions(actions: list[str]) -> list[tuple[str, str]]:
        """Parse actions list into (key, label) tuples."""
        pairs: list[tuple[str, str]] = []
        for i in range(0, len(actions) - 1, 2):
            action_key = actions[i]
            action_label = actions[i + 1]
            pairs.append((action_key, action_label))
        return pairs

    def _box_add(self, box: Any, child: Any) -> None:
        if self._gtk_major == 3:
            box.pack_start(child, False, False, 0)
        else:
            box.append(child)

    def _set_label_wrap(self, label: Any, enabled: bool) -> None:
        if self._gtk_major == 3:
            label.set_line_wrap(enabled)
        else:
            label.set_wrap(enabled)

    def _get_primary_monitor(self, gdk_module: Any) -> Any:
        display = gdk_module.Display.get_default()
        if display is None:
            return None

        if hasattr(display, "get_primary_monitor"):
            monitor = display.get_primary_monitor()
            if monitor is not None:
                return monitor

        if hasattr(display, "get_n_monitors") and hasattr(display, "get_monitor"):
            n_monitors = display.get_n_monitors()
            if n_monitors > 0:
                monitor = display.get_monitor(0)
                if monitor is not None:
                    return monitor

        if hasattr(display, "get_monitors"):
            monitors = display.get_monitors()
            if monitors and monitors.get_n_items() > 0:
                return monitors.get_item(0)

        return None

    def _replace_existing_notification(self, notification: Notification) -> None:
        if notification.replaces_id:
            self._destroy_window(
                notification.replaces_id,
                False,
                CLOSE_REASON_REPLACED,
            )

    def _create_popup_window(self, gtk_module: Any) -> Any:
        if self._gtk_major == 3:
            return gtk_module.Window(type=gtk_module.WindowType.POPUP)
        return gtk_module.Window()

    def _configure_common_window(
        self, win: Any, gdk_module: Any, opacity: float | None = None
    ) -> None:
        win.set_decorated(False)
        win.set_resizable(False)
        if opacity is not None and hasattr(win, "set_opacity"):
            win.set_opacity(opacity)
        if hasattr(win, "set_keep_above"):
            win.set_keep_above(True)
        if hasattr(win, "set_accept_focus"):
            win.set_accept_focus(False)
        if hasattr(win, "set_focus_on_map"):
            win.set_focus_on_map(False)
        if hasattr(win, "set_can_focus"):
            win.set_can_focus(False)
        if hasattr(win, "set_focusable"):
            win.set_focusable(False)
        if hasattr(win, "set_skip_taskbar_hint"):
            win.set_skip_taskbar_hint(True)
        if hasattr(win, "set_skip_pager_hint"):
            win.set_skip_pager_hint(True)
        if self._gtk_major == 3 and hasattr(gdk_module, "WindowTypeHint"):
            win.set_type_hint(gdk_module.WindowTypeHint.NOTIFICATION)

    def _present_window(self, win: Any, content: Any) -> None:
        if self._gtk_major == 3:
            win.add(content)
            win.show_all()
        else:
            win.set_child(content)
            win.present()

    def _register_window(self, notification_id: int, win: Any) -> None:
        with self._lock:
            self._windows[notification_id] = win

    def _schedule_auto_dismiss(self, notification: Notification) -> None:
        timeout_ms = (
            notification.expire_timeout
            if notification.expire_timeout > 0
            else self._DEFAULT_TIMEOUT_MS
        )
        timeout_source = self._GLib.timeout_add(
            timeout_ms,
            self._destroy_window,
            notification.id,
            True,
            CLOSE_REASON_EXPIRED,
        )
        self._timeout_sources[notification.id] = timeout_source


class ToastRenderer(_BaseGtkRenderer):
    """Renderer that displays notifications in a top-right toast.

    Prefers layer-shell integration when available, but can fall back to a
    normal GTK window so startup does not fail on systems without
    GtkLayerShell/Gtk4LayerShell.
    """

    _DEFAULT_TIMEOUT_MS = 5000
    _TOAST_HEIGHT = 120
    _TOAST_WIDTH = 420
    _TOAST_MARGIN = 12

    # ------------------------------------------------------------------ #
    # GTK-thread helpers — must only be called via GLib.idle_add          #
    # ------------------------------------------------------------------ #

    def _create_window(self, notification: Notification) -> bool:
        Gtk, Gdk, GLib = self._Gtk, self._Gdk, self._GLib
        GtkLayerShell = self._GtkLayerShell

        self._replace_existing_notification(notification)

        win = self._create_popup_window(Gtk)
        self._configure_common_window(win, Gdk)

        self._bind_click_to_dismiss(win, notification.id)

        if GtkLayerShell is not None:
            # Configure as layer-shell surface when bindings are available.
            GtkLayerShell.init_for_window(win)
            GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP)
            monitor = self._get_primary_monitor(Gdk)
            if monitor is not None:
                GtkLayerShell.set_monitor(win, monitor)

            # Position as a toast in the top-right corner.
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, False)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
            if hasattr(GtkLayerShell, "set_margin"):
                GtkLayerShell.set_margin(
                    win, GtkLayerShell.Edge.TOP, self._TOAST_MARGIN
                )
                GtkLayerShell.set_margin(
                    win, GtkLayerShell.Edge.RIGHT, self._TOAST_MARGIN
                )

            # Avoid taking keyboard focus like dunst.
            if hasattr(GtkLayerShell, "set_keyboard_mode") and hasattr(
                GtkLayerShell, "KeyboardMode"
            ):
                GtkLayerShell.set_keyboard_mode(
                    win,
                    GtkLayerShell.KeyboardMode.NONE,
                )

        # Set size
        win.set_default_size(self._TOAST_WIDTH, self._TOAST_HEIGHT)
        if GtkLayerShell is not None:
            # A zero exclusive-zone draws over existing windows instead of
            # reserving workspace space from the compositor.
            GtkLayerShell.set_exclusive_zone(win, 0)

        # Build UI
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        if notification.app_name:
            app_lbl = Gtk.Label(label=notification.app_name)
            app_lbl.set_xalign(0.0)
            app_lbl.get_style_context().add_class("dim-label")
            self._box_add(outer, app_lbl)

        if notification.summary:
            summary_lbl = Gtk.Label()
            summary_lbl.set_markup(
                f"<b>{GLib.markup_escape_text(notification.summary)}</b>"
            )
            summary_lbl.set_xalign(0.0)
            self._set_label_wrap(summary_lbl, True)
            summary_lbl.set_max_width_chars(60)
            self._box_add(outer, summary_lbl)

        if notification.body:
            body_lbl = Gtk.Label(label=notification.body)
            body_lbl.set_xalign(0.0)
            self._set_label_wrap(body_lbl, True)
            body_lbl.set_max_width_chars(60)
            self._box_add(outer, body_lbl)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_pairs = self._parse_actions(notification.actions)
        if action_pairs:
            for action_key, action_label in action_pairs:
                btn = Gtk.Button(label=action_label)
                btn.connect(
                    "clicked",
                    self._on_action_clicked,
                    notification.id,
                    action_key,
                )
                self._box_add(action_row, btn)

        if action_pairs:
            self._box_add(outer, action_row)

        self._present_window(win, outer)
        self._register_window(notification.id, win)
        self._schedule_auto_dismiss(notification)

        return False  # don't repeat idle call


class BannerRenderer(_BaseGtkRenderer):
    """Renderer that displays notifications in a centered horizontal banner.

    Prefers layer-shell integration when available, but can fall back to a
    normal GTK window so startup does not fail on systems without
    GtkLayerShell/Gtk4LayerShell.
    """

    _DEFAULT_TIMEOUT_MS = 5000
    _BANNER_HEIGHT = 112
    _BANNER_MARGIN = 0
    _BANNER_OPACITY = 0.88

    # ------------------------------------------------------------------ #
    # GTK-thread helpers — must only be called via GLib.idle_add          #
    # ------------------------------------------------------------------ #

    def _create_window(self, notification: Notification) -> bool:
        Gtk, Gdk, GLib = self._Gtk, self._Gdk, self._GLib
        GtkLayerShell = self._GtkLayerShell

        self._replace_existing_notification(notification)

        win = self._create_popup_window(Gtk)
        self._configure_common_window(win, Gdk, opacity=self._BANNER_OPACITY)

        self._bind_click_to_dismiss(win, notification.id)

        if GtkLayerShell is not None:
            # Configure as layer-shell surface when bindings are available.
            GtkLayerShell.init_for_window(win)
            GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP)
            monitor = self._get_primary_monitor(Gdk)
            if monitor is not None:
                GtkLayerShell.set_monitor(win, monitor)

            # Position as a full-width centered banner across the middle.
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, False)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
            if hasattr(GtkLayerShell, "set_margin"):
                top_margin = self._banner_top_margin(Gdk)
                GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top_margin)
                GtkLayerShell.set_margin(
                    win, GtkLayerShell.Edge.LEFT, self._BANNER_MARGIN
                )
                GtkLayerShell.set_margin(
                    win, GtkLayerShell.Edge.RIGHT, self._BANNER_MARGIN
                )

            # Avoid taking keyboard focus like dunst.
            if hasattr(GtkLayerShell, "set_keyboard_mode") and hasattr(
                GtkLayerShell, "KeyboardMode"
            ):
                GtkLayerShell.set_keyboard_mode(
                    win,
                    GtkLayerShell.KeyboardMode.NONE,
                )

        # Set size
        win.set_default_size(self._banner_width(Gdk), self._BANNER_HEIGHT)
        if GtkLayerShell is not None:
            # A zero exclusive-zone draws over existing windows instead of
            # reserving workspace space from the compositor.
            GtkLayerShell.set_exclusive_zone(win, 0)
        else:
            # Best-effort centering when layer-shell bindings are unavailable.
            self._position_fallback_window_center(win, Gdk)

        # Build UI
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        if hasattr(outer, "set_hexpand"):
            outer.set_hexpand(True)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(self._banner_horizontal_margin())
        outer.set_margin_end(self._banner_horizontal_margin())

        if notification.app_name:
            app_lbl = Gtk.Label(label=notification.app_name)
            self._center_label(Gtk, app_lbl)
            app_lbl.get_style_context().add_class("dim-label")
            self._box_add(outer, app_lbl)

        if notification.summary:
            summary_lbl = Gtk.Label()
            summary_lbl.set_markup(
                f"<b>{GLib.markup_escape_text(notification.summary)}</b>"
            )
            self._center_label(Gtk, summary_lbl)
            self._set_label_wrap(summary_lbl, True)
            summary_lbl.set_max_width_chars(140)
            self._box_add(outer, summary_lbl)

        if notification.body:
            body_lbl = Gtk.Label(label=notification.body)
            self._center_label(Gtk, body_lbl)
            self._set_label_wrap(body_lbl, True)
            body_lbl.set_max_width_chars(140)
            self._box_add(outer, body_lbl)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if hasattr(Gtk, "Align") and hasattr(Gtk.Align, "CENTER"):
            action_row.set_halign(Gtk.Align.CENTER)
        action_pairs = self._parse_actions(notification.actions)
        if action_pairs:
            for action_key, action_label in action_pairs:
                btn = Gtk.Button(label=action_label)
                btn.connect(
                    "clicked",
                    self._on_action_clicked,
                    notification.id,
                    action_key,
                )
                self._box_add(action_row, btn)

        if action_pairs:
            self._box_add(outer, action_row)

        self._present_window(win, outer)
        self._register_window(notification.id, win)
        self._schedule_auto_dismiss(notification)

        return False  # don't repeat idle call

    def _banner_width(self, gdk_module: Any) -> int:
        monitor = self._get_primary_monitor(gdk_module)
        if monitor is None or not hasattr(monitor, "get_geometry"):
            return 1600

        geometry = monitor.get_geometry()
        return min(geometry.width, 1600)

    def _banner_top_margin(self, gdk_module: Any) -> int:
        monitor = self._get_primary_monitor(gdk_module)
        if monitor is None or not hasattr(monitor, "get_geometry"):
            return 0

        geometry = monitor.get_geometry()
        return max(0, (geometry.height - self._BANNER_HEIGHT) // 2)

    def _banner_horizontal_margin(self) -> int:
        return 24

    def _position_fallback_window_center(self, win: Any, gdk_module: Any) -> None:
        if not hasattr(win, "move"):
            return

        monitor = self._get_primary_monitor(gdk_module)
        if monitor is None or not hasattr(monitor, "get_geometry"):
            return

        geometry = monitor.get_geometry()
        banner_width = self._banner_width(gdk_module)
        center_x = max(0, geometry.x + (geometry.width - banner_width) // 2)
        center_y = max(0, geometry.y + (geometry.height - self._BANNER_HEIGHT) // 2)
        win.move(center_x, center_y)

    def _center_label(self, gtk_module: Any, label: Any) -> None:
        label.set_xalign(0.5)
        if hasattr(gtk_module, "Justification") and hasattr(label, "set_justify"):
            label.set_justify(gtk_module.Justification.CENTER)
        if hasattr(gtk_module, "Align") and hasattr(label, "set_halign"):
            label.set_halign(gtk_module.Align.CENTER)
