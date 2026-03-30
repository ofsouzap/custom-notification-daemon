#!/usr/bin/env python3

import sys
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from gi_support import (
    BoxApi,
    DisplayApi,
    GdkApi,
    GestureClickApi,
    GlibApi,
    GtkApi,
    LabelApi,
    LayerShellApi,
    ListModelApi,
    MonitorApi,
    WindowApi,
)
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

        from gi.repository import Gtk, Gdk, GLib  # type: ignore[attr-defined]

        layer_shell = None
        if gtk_major == 3:
            for version in ("0.1", "0"):
                try:
                    gi.require_version("GtkLayerShell", version)
                    from gi.repository import GtkLayerShell  # type: ignore[attr-defined]

                    layer_shell = GtkLayerShell
                    break
                except ValueError:
                    continue
        else:
            for version in ("1.0", "0"):
                try:
                    gi.require_version("Gtk4LayerShell", version)
                    from gi.repository import Gtk4LayerShell  # type: ignore[attr-defined]

                    layer_shell = Gtk4LayerShell
                    break
                except ValueError:
                    continue

        self._gtk_major = gtk_major
        self._gtk_api = GtkApi.from_module(Gtk)
        self._gdk_api = GdkApi.from_module(Gdk)
        self._glib_api = GlibApi.from_module(GLib)
        self._layer_shell_api = LayerShellApi.from_module(layer_shell)
        self._main_loop = None

        if self._layer_shell_api is None:
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
            if self._gtk_api.main is None:
                raise RuntimeError("Gtk.main is unavailable")
            gtk_thread = threading.Thread(target=self._gtk_api.main, daemon=True)
        else:
            if self._glib_api.main_loop_ctor is None:
                raise RuntimeError("GLib.MainLoop is unavailable")
            self._main_loop = self._glib_api.main_loop_ctor()
            gtk_thread = threading.Thread(target=self._main_loop.run, daemon=True)
        gtk_thread.start()

    def show(self, notification: Notification) -> None:
        self._run_on_main_thread(self._create_window, notification)

    def _run_on_main_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        idle_add = self._glib_api.idle_add
        if idle_add is not None:
            idle_add(callback, *args)
            return
        callback(*args)

    @abstractmethod
    def _create_window(self, notification: Notification) -> bool:
        """Create and show renderer-specific UI for a notification."""
        ...

    def close(self, notification_id: int) -> None:
        self._run_on_main_thread(
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
                if self._glib_api.source_remove is not None:
                    self._glib_api.source_remove(timeout_source)
            win.destroy()
            if emit_closed:
                self._on_closed(notification_id, close_reason)

        return False

    def _bind_click_to_dismiss(self, widget: Any, notification_id: int) -> None:
        win_api = WindowApi.from_window(widget)
        if self._gtk_major == 3:
            if (
                win_api.add_events is not None
                and self._gdk_api.event_mask_button_press is not None
            ):
                win_api.add_events(self._gdk_api.event_mask_button_press)
            if win_api.connect is not None:
                win_api.connect(
                    "button-press-event",
                    self._on_notification_clicked_gtk3,
                    notification_id,
                )
            return

        if (
            self._gtk_major == 4
            and self._gtk_api.gesture_click_ctor is not None
            and win_api.add_controller is not None
        ):
            click = self._gtk_api.gesture_click_ctor()
            click_api = GestureClickApi.from_gesture(click)
            if click_api.set_button is not None:
                click_api.set_button(1)
            if click_api.connect is not None:
                click_api.connect(
                    "pressed",
                    self._on_notification_clicked_gtk4,
                    notification_id,
                )
            win_api.add_controller(click)

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

    def _get_primary_monitor(self) -> Any:
        if self._gdk_api.display_get_default is None:
            return None
        display = self._gdk_api.display_get_default()
        if display is None:
            return None

        display_api = DisplayApi.from_display(display)

        if display_api.get_primary_monitor is not None:
            monitor = display_api.get_primary_monitor()
            if monitor is not None:
                return monitor

        if display_api.get_n_monitors and display_api.get_monitor:
            n_monitors = display_api.get_n_monitors()
            if n_monitors > 0:
                monitor = display_api.get_monitor(0)
                if monitor is not None:
                    return monitor

        if display_api.get_monitors:
            monitors = display_api.get_monitors()
            if monitors is not None:
                model_api = ListModelApi.from_model(monitors)
                if model_api.get_n_items and model_api.get_item:
                    if model_api.get_n_items() > 0:
                        return model_api.get_item(0)

        return None

    def _replace_existing_notification(self, notification: Notification) -> None:
        if notification.replaces_id:
            self._destroy_window(
                notification.replaces_id,
                False,
                CLOSE_REASON_REPLACED,
            )

    def _create_popup_window(self) -> Any:
        if self._gtk_api.window_ctor is None:
            return None
        if self._gtk_major == 3 and self._gtk_api.window_type_popup is not None:
            return self._gtk_api.window_ctor(type=self._gtk_api.window_type_popup)
        return self._gtk_api.window_ctor()

    def _configure_common_window(self, win: Any, opacity: float | None = None) -> None:
        win_api = WindowApi.from_window(win)
        win.set_decorated(False)
        win.set_resizable(False)
        if opacity is not None and win_api.set_opacity is not None:
            win_api.set_opacity(opacity)
        if win_api.set_keep_above is not None:
            win_api.set_keep_above(True)
        if win_api.set_accept_focus is not None:
            win_api.set_accept_focus(False)
        if win_api.set_focus_on_map is not None:
            win_api.set_focus_on_map(False)
        if win_api.set_can_focus is not None:
            win_api.set_can_focus(False)
        if win_api.set_focusable is not None:
            win_api.set_focusable(False)
        if win_api.set_skip_taskbar_hint is not None:
            win_api.set_skip_taskbar_hint(True)
        if win_api.set_skip_pager_hint is not None:
            win_api.set_skip_pager_hint(True)
        if (
            self._gtk_major == 3
            and win_api.set_type_hint is not None
            and self._gdk_api.window_type_notification is not None
        ):
            win_api.set_type_hint(self._gdk_api.window_type_notification)

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
        if self._glib_api.timeout_add is None:
            return
        timeout_source = self._glib_api.timeout_add(
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
        gtk_api = self._gtk_api
        glib_api = self._glib_api
        layer_shell_api = self._layer_shell_api

        self._replace_existing_notification(notification)

        win = self._create_popup_window()
        if win is None:
            return False
        self._configure_common_window(win)

        self._bind_click_to_dismiss(win, notification.id)

        if layer_shell_api is not None:
            # Configure as layer-shell surface when bindings are available.
            if layer_shell_api.init_for_window is not None:
                layer_shell_api.init_for_window(win)
            if (
                layer_shell_api.set_layer is not None
                and layer_shell_api.layer_top is not None
            ):
                layer_shell_api.set_layer(win, layer_shell_api.layer_top)
            monitor = self._get_primary_monitor()
            if monitor is not None and layer_shell_api.set_monitor is not None:
                layer_shell_api.set_monitor(win, monitor)

            # Position as a toast in the top-right corner.
            if layer_shell_api.set_anchor is not None:
                if layer_shell_api.edge_top is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_top, True)
                if layer_shell_api.edge_left is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_left, False)
                if layer_shell_api.edge_right is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_right, True)
            if layer_shell_api.set_margin is not None:
                if layer_shell_api.edge_top is not None:
                    layer_shell_api.set_margin(
                        win, layer_shell_api.edge_top, self._TOAST_MARGIN
                    )
                if layer_shell_api.edge_right is not None:
                    layer_shell_api.set_margin(
                        win, layer_shell_api.edge_right, self._TOAST_MARGIN
                    )

            # Avoid taking keyboard focus like dunst.
            if (
                layer_shell_api.set_keyboard_mode is not None
                and layer_shell_api.keyboard_mode_none is not None
            ):
                layer_shell_api.set_keyboard_mode(
                    win, layer_shell_api.keyboard_mode_none
                )

        # Set size
        win.set_default_size(self._TOAST_WIDTH, self._TOAST_HEIGHT)
        if (
            layer_shell_api is not None
            and layer_shell_api.set_exclusive_zone is not None
        ):
            # A zero exclusive-zone draws over existing windows instead of
            # reserving workspace space from the compositor.
            layer_shell_api.set_exclusive_zone(win, 0)

        # Build UI
        if gtk_api.box_ctor is None or gtk_api.orientation_vertical is None:
            return False
        outer = gtk_api.box_ctor(orientation=gtk_api.orientation_vertical, spacing=4)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        if notification.app_name:
            if gtk_api.label_ctor is None:
                return False
            app_lbl = gtk_api.label_ctor(label=notification.app_name)
            app_lbl.set_xalign(0.0)
            app_lbl.get_style_context().add_class("dim-label")
            self._box_add(outer, app_lbl)

        if notification.summary:
            if gtk_api.label_ctor is None:
                return False
            summary_lbl = gtk_api.label_ctor()
            escaped_summary = notification.summary
            if glib_api.markup_escape_text is not None:
                escaped_summary = glib_api.markup_escape_text(notification.summary)
            summary_lbl.set_markup(f"<b>{escaped_summary}</b>")
            summary_lbl.set_xalign(0.0)
            self._set_label_wrap(summary_lbl, True)
            summary_lbl.set_max_width_chars(60)
            self._box_add(outer, summary_lbl)

        if notification.body:
            if gtk_api.label_ctor is None:
                return False
            body_lbl = gtk_api.label_ctor(label=notification.body)
            body_lbl.set_xalign(0.0)
            self._set_label_wrap(body_lbl, True)
            body_lbl.set_max_width_chars(60)
            self._box_add(outer, body_lbl)

        if gtk_api.box_ctor is None or gtk_api.orientation_horizontal is None:
            return False
        action_row = gtk_api.box_ctor(
            orientation=gtk_api.orientation_horizontal,
            spacing=6,
        )
        action_pairs = self._parse_actions(notification.actions)
        if action_pairs:
            for action_key, action_label in action_pairs:
                if gtk_api.button_ctor is None:
                    return False
                btn = gtk_api.button_ctor(label=action_label)
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
        gtk_api = self._gtk_api
        glib_api = self._glib_api
        layer_shell_api = self._layer_shell_api

        self._replace_existing_notification(notification)

        win = self._create_popup_window()
        if win is None:
            return False
        self._configure_common_window(win, opacity=self._BANNER_OPACITY)

        self._bind_click_to_dismiss(win, notification.id)

        if layer_shell_api is not None:
            # Configure as layer-shell surface when bindings are available.
            if layer_shell_api.init_for_window is not None:
                layer_shell_api.init_for_window(win)
            if (
                layer_shell_api.set_layer is not None
                and layer_shell_api.layer_top is not None
            ):
                layer_shell_api.set_layer(win, layer_shell_api.layer_top)
            monitor = self._get_primary_monitor()
            if monitor is not None and layer_shell_api.set_monitor is not None:
                layer_shell_api.set_monitor(win, monitor)

            # Position as a full-width centered banner across the middle.
            if layer_shell_api.set_anchor is not None:
                if layer_shell_api.edge_top is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_top, True)
                if layer_shell_api.edge_bottom is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_bottom, False)
                if layer_shell_api.edge_left is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_left, True)
                if layer_shell_api.edge_right is not None:
                    layer_shell_api.set_anchor(win, layer_shell_api.edge_right, True)
            if layer_shell_api.set_margin is not None:
                top_margin = self._banner_top_margin()
                if layer_shell_api.edge_top is not None:
                    layer_shell_api.set_margin(
                        win, layer_shell_api.edge_top, top_margin
                    )
                if layer_shell_api.edge_left is not None:
                    layer_shell_api.set_margin(
                        win, layer_shell_api.edge_left, self._BANNER_MARGIN
                    )
                if layer_shell_api.edge_right is not None:
                    layer_shell_api.set_margin(
                        win, layer_shell_api.edge_right, self._BANNER_MARGIN
                    )

            # Avoid taking keyboard focus like dunst.
            if (
                layer_shell_api.set_keyboard_mode is not None
                and layer_shell_api.keyboard_mode_none is not None
            ):
                layer_shell_api.set_keyboard_mode(
                    win, layer_shell_api.keyboard_mode_none
                )

        # Set size
        win.set_default_size(self._banner_width(), self._BANNER_HEIGHT)
        if (
            layer_shell_api is not None
            and layer_shell_api.set_exclusive_zone is not None
        ):
            # A zero exclusive-zone draws over existing windows instead of
            # reserving workspace space from the compositor.
            layer_shell_api.set_exclusive_zone(win, 0)
        else:
            # Best-effort centering when layer-shell bindings are unavailable.
            self._position_fallback_window_center(win)

        # Build UI
        if gtk_api.box_ctor is None or gtk_api.orientation_vertical is None:
            return False
        outer = gtk_api.box_ctor(orientation=gtk_api.orientation_vertical, spacing=4)
        outer_api = BoxApi.from_box(outer)
        if outer_api.set_hexpand is not None:
            outer_api.set_hexpand(True)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(self._banner_horizontal_margin())
        outer.set_margin_end(self._banner_horizontal_margin())

        if notification.app_name:
            if gtk_api.label_ctor is None:
                return False
            app_lbl = gtk_api.label_ctor(label=notification.app_name)
            self._center_label(app_lbl)
            app_lbl.get_style_context().add_class("dim-label")
            self._box_add(outer, app_lbl)

        if notification.summary:
            if gtk_api.label_ctor is None:
                return False
            summary_lbl = gtk_api.label_ctor()
            escaped_summary = notification.summary
            if glib_api.markup_escape_text is not None:
                escaped_summary = glib_api.markup_escape_text(notification.summary)
            summary_lbl.set_markup(f"<b>{escaped_summary}</b>")
            self._center_label(summary_lbl)
            self._set_label_wrap(summary_lbl, True)
            summary_lbl.set_max_width_chars(140)
            self._box_add(outer, summary_lbl)

        if notification.body:
            if gtk_api.label_ctor is None:
                return False
            body_lbl = gtk_api.label_ctor(label=notification.body)
            self._center_label(body_lbl)
            self._set_label_wrap(body_lbl, True)
            body_lbl.set_max_width_chars(140)
            self._box_add(outer, body_lbl)

        if gtk_api.box_ctor is None or gtk_api.orientation_horizontal is None:
            return False
        action_row = gtk_api.box_ctor(
            orientation=gtk_api.orientation_horizontal,
            spacing=6,
        )
        action_row_api = BoxApi.from_box(action_row)
        if action_row_api.set_halign is not None and gtk_api.align_center is not None:
            action_row_api.set_halign(gtk_api.align_center)
        action_pairs = self._parse_actions(notification.actions)
        if action_pairs:
            for action_key, action_label in action_pairs:
                if gtk_api.button_ctor is None:
                    return False
                btn = gtk_api.button_ctor(label=action_label)
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

    def _banner_width(self) -> int:
        monitor = self._get_primary_monitor()
        if monitor is None:
            return 1600

        monitor_api = MonitorApi.from_monitor(monitor)
        if monitor_api.get_geometry is None:
            return 1600
        geometry = monitor_api.get_geometry()
        return min(geometry.width, 1600)

    def _banner_top_margin(self) -> int:
        monitor = self._get_primary_monitor()
        if monitor is None:
            return 0

        monitor_api = MonitorApi.from_monitor(monitor)
        if monitor_api.get_geometry is None:
            return 0
        geometry = monitor_api.get_geometry()
        return max(0, (geometry.height - self._BANNER_HEIGHT) // 2)

    def _banner_horizontal_margin(self) -> int:
        return 24

    def _position_fallback_window_center(self, win: Any) -> None:
        win_api = WindowApi.from_window(win)
        if win_api.move is None:
            return

        monitor = self._get_primary_monitor()
        if monitor is None:
            return

        monitor_api = MonitorApi.from_monitor(monitor)
        if monitor_api.get_geometry is None:
            return
        geometry = monitor_api.get_geometry()
        banner_width = self._banner_width()
        center_x = max(0, geometry.x + (geometry.width - banner_width) // 2)
        center_y = max(0, geometry.y + (geometry.height - self._BANNER_HEIGHT) // 2)
        win_api.move(center_x, center_y)

    def _center_label(self, label: Any) -> None:
        label.set_xalign(0.5)
        label_api = LabelApi.from_label(label)
        if (
            label_api.set_justify is not None
            and self._gtk_api.justification_center is not None
        ):
            label_api.set_justify(self._gtk_api.justification_center)
        if label_api.set_halign is not None and self._gtk_api.align_center is not None:
            label_api.set_halign(self._gtk_api.align_center)
