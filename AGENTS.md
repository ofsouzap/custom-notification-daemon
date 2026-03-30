# AGENTS.md

This file is a lightweight handoff for future coding-agent sessions.
Keep this file up to date where needed.
Update the TODO section below whenever scope or status changes.

## Project Snapshot

- Name: custom-notification-daemon
- Goal: run a custom `org.freedesktop.Notifications` daemon for Wayland/Sway.
- Current UX target: toast-like notifications in the top-right, layered above windows (no layout reservation).

## Core Files

- `main.py`: app entrypoint; wires daemon + renderer.
- `notifications.py`: D-Bus protocol layer and daemon base class.
- `renderer.py`: GTK renderer and layer-shell integration.
- `apt-dependencies.txt`: required apt runtime dependencies.
- `apt-dev-dependencies.txt`: apt development/build dependencies.
- `requirements.txt`: Python dependencies.
- `gi_support/wrappers.py`: typed wrappers for optional GI APIs and constants.
- `pyrightconfig.json`: pyright settings for GI-heavy environment.
- `debian/`: Debian packaging files for `.deb` builds.

## Runtime Behavior Notes

- The daemon must own `org.freedesktop.Notifications`.
- If another notification daemon is running (dunst/mako/etc.), startup fails by design.
- On Wayland/Sway, true non-window-overlay behavior requires GtkLayerShell.

## Environment Setup

Install system packages:

sudo xargs -a apt-dependencies.txt apt install -y

Create venv with system site packages (important for apt-installed GI libs):

/usr/bin/python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt

Run daemon:

source .venv/bin/activate
python main.py run

## Renderer Decisions (Current)

- GTK version is detected dynamically (prefers GTK3, falls back to GTK4).
- GtkLayerShell is optional; if unavailable, renderer falls back to normal GTK windows.
- GtkLayerShell version handling includes `0.1` and `0` for compatibility.
- Toast positioning uses top-right anchors and margins.
- Exclusive zone is set to `0` so compositor does not shrink workspace.
- Keyboard mode is set to `NONE` when supported to avoid focus grab.

## D-Bus / Protocol Notes

- Signal emitters in `notifications.py` must return a list body.
- Returning tuples for dbus-next signals caused `SignatureBodyMismatchError` in earlier iteration.

## Type Checking Notes

- GI imports are dynamic (`gi.repository`) and not fully statically discoverable.
- Optional GI methods/constants are wrapped in `gi_support/wrappers.py` and typed as nullable callables/values.
- Renderer code should use wrappers instead of ad-hoc `hasattr` checks for optional API paths.
- `pyrightconfig.json` keeps `reportMissingModuleSource: none` to reduce GI import noise.

## Quick Troubleshooting

If startup says another daemon is running:

pkill -x dunst || true
pkill -x mako || true
systemctl --user stop dunst.service 2>/dev/null || true
systemctl --user stop mako.service 2>/dev/null || true

If renderer warns it is running without GtkLayerShell:

- Verify apt packages from `apt-dependencies.txt` are installed.
- Recreate venv with `--system-site-packages`.

If `dpkg-buildpackage` fails early on source format:

- Ensure `debian/source/format` is exactly `3.0 (native)`.

If built package contains a wrong launcher path:

- Keep launcher mapping as `debian/custom-notification-daemon-launcher usr/bin/`.
- Keep symlink in `debian/custom-notification-daemon.links` from
  `/usr/bin/custom-notification-daemon-launcher` to `/usr/bin/custom-notification-daemon`.

## TODO (Keep Up To Date)

- [ ] Implement urgency levels end-to-end (respect `hints["urgency"]` for timeout, styling, and behavior).
- [x] Make installation easy and reliable baseline: Debian package skeleton (`debian/`) with launcher.
- [ ] Improve install UX further (for example: one-command helper script, release automation, and polished first-run guidance).
- [ ] Add multiple renderer display modes and config-file selection between renderers.
- [x] Improve command-line interface baseline: Click-based CLI with run/version/service helpers.
- [x] Add GitHub Actions workflow to build `.deb` package artifacts on push/release.
- [ ] Improve visual design to be nicer and more colorful (better spacing, typography, accent colors).
- [ ] Tie visual styling to urgency levels (for example: subtle normal, highlighted critical).
