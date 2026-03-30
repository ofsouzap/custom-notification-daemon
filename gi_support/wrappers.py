from dataclasses import dataclass
from typing import Any, Callable


def _optional_callable(obj: Any, name: str) -> Callable[..., Any] | None:
    value = getattr(obj, name, None)
    if callable(value):
        return value
    return None


def _nested_attr(obj: Any, *parts: str) -> Any | None:
    current = obj
    for part in parts:
        current = getattr(current, part, None)
        if current is None:
            return None
    return current


@dataclass(frozen=True)
class WindowApi:
    set_keep_above: Callable[[bool], Any] | None
    set_accept_focus: Callable[[bool], Any] | None
    set_focus_on_map: Callable[[bool], Any] | None
    set_can_focus: Callable[[bool], Any] | None
    set_focusable: Callable[[bool], Any] | None
    set_skip_taskbar_hint: Callable[[bool], Any] | None
    set_skip_pager_hint: Callable[[bool], Any] | None
    set_type_hint: Callable[[Any], Any] | None
    add_events: Callable[[Any], Any] | None
    connect: Callable[..., Any] | None
    add_controller: Callable[[Any], Any] | None
    set_opacity: Callable[[float], Any] | None
    move: Callable[[int, int], Any] | None

    @classmethod
    def from_window(cls, window: Any) -> "WindowApi":
        return cls(
            set_keep_above=_optional_callable(window, "set_keep_above"),
            set_accept_focus=_optional_callable(window, "set_accept_focus"),
            set_focus_on_map=_optional_callable(window, "set_focus_on_map"),
            set_can_focus=_optional_callable(window, "set_can_focus"),
            set_focusable=_optional_callable(window, "set_focusable"),
            set_skip_taskbar_hint=_optional_callable(window, "set_skip_taskbar_hint"),
            set_skip_pager_hint=_optional_callable(window, "set_skip_pager_hint"),
            set_type_hint=_optional_callable(window, "set_type_hint"),
            add_events=_optional_callable(window, "add_events"),
            connect=_optional_callable(window, "connect"),
            add_controller=_optional_callable(window, "add_controller"),
            set_opacity=_optional_callable(window, "set_opacity"),
            move=_optional_callable(window, "move"),
        )


@dataclass(frozen=True)
class GtkApi:
    main: Callable[[], Any] | None
    window_ctor: Callable[..., Any] | None
    box_ctor: Callable[..., Any] | None
    label_ctor: Callable[..., Any] | None
    button_ctor: Callable[..., Any] | None
    orientation_vertical: Any | None
    orientation_horizontal: Any | None
    window_type_popup: Any | None
    gesture_click_ctor: Callable[[], Any] | None
    align_center: Any | None
    justification_center: Any | None

    @classmethod
    def from_module(cls, gtk_module: Any) -> "GtkApi":
        return cls(
            main=_optional_callable(gtk_module, "main"),
            window_ctor=_optional_callable(gtk_module, "Window"),
            box_ctor=_optional_callable(gtk_module, "Box"),
            label_ctor=_optional_callable(gtk_module, "Label"),
            button_ctor=_optional_callable(gtk_module, "Button"),
            orientation_vertical=_nested_attr(gtk_module, "Orientation", "VERTICAL"),
            orientation_horizontal=_nested_attr(
                gtk_module, "Orientation", "HORIZONTAL"
            ),
            window_type_popup=_nested_attr(gtk_module, "WindowType", "POPUP"),
            gesture_click_ctor=_nested_attr(gtk_module, "GestureClick"),
            align_center=_nested_attr(gtk_module, "Align", "CENTER"),
            justification_center=_nested_attr(gtk_module, "Justification", "CENTER"),
        )


@dataclass(frozen=True)
class GdkApi:
    display_get_default: Callable[[], Any] | None
    window_type_notification: Any | None
    event_mask_button_press: Any | None

    @classmethod
    def from_module(cls, gdk_module: Any) -> "GdkApi":
        return cls(
            display_get_default=_nested_attr(gdk_module, "Display", "get_default"),
            window_type_notification=_nested_attr(
                gdk_module, "WindowTypeHint", "NOTIFICATION"
            ),
            event_mask_button_press=_nested_attr(
                gdk_module, "EventMask", "BUTTON_PRESS_MASK"
            ),
        )


@dataclass(frozen=True)
class GlibApi:
    main_loop_ctor: Callable[[], Any] | None
    idle_add: Callable[..., int] | None
    timeout_add: Callable[..., int] | None
    source_remove: Callable[[int], Any] | None
    markup_escape_text: Callable[[str], str] | None

    @classmethod
    def from_module(cls, glib_module: Any) -> "GlibApi":
        return cls(
            main_loop_ctor=_optional_callable(glib_module, "MainLoop"),
            idle_add=_optional_callable(glib_module, "idle_add"),
            timeout_add=_optional_callable(glib_module, "timeout_add"),
            source_remove=_optional_callable(glib_module, "source_remove"),
            markup_escape_text=_optional_callable(glib_module, "markup_escape_text"),
        )


@dataclass(frozen=True)
class LayerShellApi:
    init_for_window: Callable[[Any], Any] | None
    set_layer: Callable[[Any, Any], Any] | None
    set_monitor: Callable[[Any, Any], Any] | None
    set_anchor: Callable[[Any, Any, bool], Any] | None
    set_margin: Callable[[Any, Any, int], Any] | None
    set_keyboard_mode: Callable[[Any, Any], Any] | None
    set_exclusive_zone: Callable[[Any, int], Any] | None
    layer_top: Any | None
    edge_top: Any | None
    edge_left: Any | None
    edge_right: Any | None
    edge_bottom: Any | None
    keyboard_mode_none: Any | None

    @classmethod
    def from_module(cls, module: Any | None) -> "LayerShellApi | None":
        if module is None:
            return None
        return cls(
            init_for_window=_optional_callable(module, "init_for_window"),
            set_layer=_optional_callable(module, "set_layer"),
            set_monitor=_optional_callable(module, "set_monitor"),
            set_anchor=_optional_callable(module, "set_anchor"),
            set_margin=_optional_callable(module, "set_margin"),
            set_keyboard_mode=_optional_callable(module, "set_keyboard_mode"),
            set_exclusive_zone=_optional_callable(module, "set_exclusive_zone"),
            layer_top=_nested_attr(module, "Layer", "TOP"),
            edge_top=_nested_attr(module, "Edge", "TOP"),
            edge_left=_nested_attr(module, "Edge", "LEFT"),
            edge_right=_nested_attr(module, "Edge", "RIGHT"),
            edge_bottom=_nested_attr(module, "Edge", "BOTTOM"),
            keyboard_mode_none=_nested_attr(module, "KeyboardMode", "NONE"),
        )


@dataclass(frozen=True)
class DisplayApi:
    get_primary_monitor: Callable[[], Any] | None
    get_n_monitors: Callable[[], int] | None
    get_monitor: Callable[[int], Any] | None
    get_monitors: Callable[[], Any] | None

    @classmethod
    def from_display(cls, display: Any) -> "DisplayApi":
        return cls(
            get_primary_monitor=_optional_callable(display, "get_primary_monitor"),
            get_n_monitors=_optional_callable(display, "get_n_monitors"),
            get_monitor=_optional_callable(display, "get_monitor"),
            get_monitors=_optional_callable(display, "get_monitors"),
        )


@dataclass(frozen=True)
class ListModelApi:
    get_n_items: Callable[[], int] | None
    get_item: Callable[[int], Any] | None

    @classmethod
    def from_model(cls, model: Any) -> "ListModelApi":
        return cls(
            get_n_items=_optional_callable(model, "get_n_items"),
            get_item=_optional_callable(model, "get_item"),
        )


@dataclass(frozen=True)
class MonitorApi:
    get_geometry: Callable[[], Any] | None

    @classmethod
    def from_monitor(cls, monitor: Any) -> "MonitorApi":
        return cls(get_geometry=_optional_callable(monitor, "get_geometry"))


@dataclass(frozen=True)
class BoxApi:
    set_halign: Callable[[Any], Any] | None
    set_hexpand: Callable[[bool], Any] | None

    @classmethod
    def from_box(cls, box: Any) -> "BoxApi":
        return cls(
            set_halign=_optional_callable(box, "set_halign"),
            set_hexpand=_optional_callable(box, "set_hexpand"),
        )


@dataclass(frozen=True)
class LabelApi:
    set_justify: Callable[[Any], Any] | None
    set_halign: Callable[[Any], Any] | None

    @classmethod
    def from_label(cls, label: Any) -> "LabelApi":
        return cls(
            set_justify=_optional_callable(label, "set_justify"),
            set_halign=_optional_callable(label, "set_halign"),
        )


@dataclass(frozen=True)
class GestureClickApi:
    set_button: Callable[[int], Any] | None
    connect: Callable[..., Any] | None

    @classmethod
    def from_gesture(cls, gesture: Any) -> "GestureClickApi":
        return cls(
            set_button=_optional_callable(gesture, "set_button"),
            connect=_optional_callable(gesture, "connect"),
        )
