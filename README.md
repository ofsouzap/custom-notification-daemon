# Custom notification daemon

My custom notification daemon script. Just for fun. Designed for running on Wayland sway Ubuntu machine.

## Setup

### 1. System packages

The file `apt-dependencies.txt` contains the apt packages required for this project.
I'm not bothering yet with version pinning.
These can be installed with the command,

```bash
sudo xargs -a apt-dependencies.txt apt install -y
```

The file `apt-dev-dependencies.txt` also exists, for dependencies that are only for development, e.g. build tools.

Install those with:

```bash
sudo xargs -a apt-dev-dependencies.txt apt install -y
```

### 2. (Optional) Virtual environment setup

If creating a virtual environment, use the `--system-site-packages` flag,
and only do so after installing the apt packages, so that the venv can use them:

```bash
python -m venv --system-site-packages .venv
```

NOTE TO SELF: make sure to use the apt-installed Python binary, not the nix-installed one, otherwise `--system-site-packagaes` won't do what you want it to. Therefore use `/usr/bin/python3 -m venv --system-site-packages .venv`.

Then activate it:

```bash
source ./.venv/bin/activate
```

### 3. pip requirements

Then the Python requirements can be installed with the `requirements.txt` file,

```bash
pip install -r requirements.txt
```

## CLI usage

The daemon has a Click-based CLI:

```bash
python main.py --help
python main.py run
python main.py version
python main.py service-hints
```

Running without a subcommand still starts the daemon:

```bash
python main.py run
```

Renderer options:

```bash
python main.py run --renderer toast
python main.py run --renderer banner
```

## Debian package (.deb) building

This repository includes a minimal `debian/` packaging setup.
You can build a `.deb` and install it on other Ubuntu machines.

### 1. Install package build tools

```bash
sudo xargs -a apt-dev-dependencies.txt apt install -y
```

### 2. Build the package

From the repository root:

```bash
dpkg-buildpackage -us -uc
```

Or use the helper script to build and copy generated artifacts into
`./build-artifacts/` inside this repo:

```bash
./scripts/build-deb.sh
```

The helper script also validates that `main.py` version and
`debian/changelog` package version match before building.

This produces a package file in the parent directory, for example:

`../custom-notification-daemon_0.2.0_all.deb`

### 3. Install the package

```bash
sudo apt install ../custom-notification-daemon_0.2.0_all.deb
```

The package installs:

- daemon code in `/usr/lib/custom-notification-daemon/`
- launcher at `/usr/bin/custom-notification-daemon`

Packaging implementation note:

- launcher source file is `debian/custom-notification-daemon-launcher`
- `debian/custom-notification-daemon.links` creates
	`/usr/bin/custom-notification-daemon` as a symlink target for stable UX

### 4. Disable existing notification daemon

If another notifications daemon is active, disable it first:

```bash
systemctl --user disable --now dunst.service 2>/dev/null || true
systemctl --user disable --now mako.service 2>/dev/null || true
```

### 5. Start from Sway login (instead of dunst)

In your Sway config, ensure this line exists:

```bash
exec_always --no-startup-id custom-notification-daemon run
```
