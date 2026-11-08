# scripts/

Utility scripts for everyday terminal work. Plain bash, no dependencies
beyond standard Linux tools.

Currently contains:

- [podman-pods.sh](#podman-pods) — interactive manager for podman container definitions

## Setup

Make the scripts executable (already done, but re-run if you copy them):

```bash
chmod +x ~/projects/scripts/*.sh
```

Optionally add the directory to your `PATH` so you can run them from anywhere:

```bash
echo 'export PATH="$HOME/projects/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

After that, `podman-pods` works from any directory. Without the `PATH`
change, run it as `./podman-pods.sh` from inside this folder.

---

## podman-pods

Interactive manager for podman container definitions. Keeps everything in
`podman.pods` (INI-style, hand-editable) in the script's own folder.

```
Usage: podman-pods.sh
```

No arguments — it's a menu-driven program.

### First run

Creates `podman.pods` and immediately walks you through defining the first
pod. From then on, every run opens the menu.

### The menu

Lists saved pods by name (with their image):

```
=== Podman Pods ===
  1. myweb                (docker.io/library/nginx:latest)
  2. alpine-sleeper       (docker.io/library/alpine:3.20)
  3. Create new pod
  4. Exit
```

Pick a pod to get a sub-menu:

```
Pod: myweb (docker.io/library/nginx:latest)
  [r]un  [e]dit  [b]ack
```

The last two options are always "Create new pod" and "Exit", numbered
after the pods.

### The walkthrough (create and edit)

Both create and edit walk through the same options:

- **container name** — validated (letters, numbers, `._-`), must be unique
- **image** — e.g. `docker.io/library/nginx:latest` (required)
- **port mappings** — `host:container` (a bare host port is also accepted)
- **volume mounts** — `host:container`
- **environment variables** — `KEY=VALUE`
- **command to run** — optional, overrides the image's default

For the list options (ports, volumes, env vars) you get a numbered list
where you can:

- enter a **number** to remove that item
- enter **`a`** to add a new one (Enter cancels the add)
- press **Enter** to finish

In edit mode, pressing Enter at the name/image/command prompts keeps the
current value. Renaming a pod is allowed (the section in `podman.pods` is
updated).

### Running a pod

If a container with the pod's name already exists, you're offered:

- **s** — start it (then follow with `podman logs -f <name>`)
- **r** — remove and recreate it
- **c** — cancel

Otherwise you choose **foreground** (`-it`, Enter) or **detached** (`d`,
`-d`). The exact `podman run` command is printed before it runs.

### The config file

`podman.pods` lives next to the script and looks like:

```ini
[myweb]
image=nginx:latest
port=8080:80
volume=/srv/www:/usr/share/nginx/html
env=MODE=fast
command=
```

One `[name]` section per pod. `port=`, `volume=`, and `env=` lines can be
repeated. The file is hand-editable — just keep the format.

### Notes

- Looks for `podman.pods` in the **script's folder**, not the current
  directory.
- If podman isn't installed, you get a warning at startup. You can still
  create and edit definitions; only "run" is blocked, with a clear error.
- Set `PODMAN_BIN` to point at a non-default podman binary:
  `PODMAN_BIN=/usr/local/bin/podman ./podman-pods.sh`
- `Ctrl-D` (EOF) exits cleanly at any prompt.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Warning: podman is not installed` | `sudo apt install podman` (or set `PODMAN_BIN`) |
| `Container '<name>' already exists` on every run | Pick **r** to remove and recreate, or **s** to start the existing one |
| `The input device is not a TTY` warning | Harmless — appears when running through a pipe/CI instead of a real terminal |
| Permission denied on a port below 1024 | Use a host port above 1024, or run the script with `sudo` |
| Image not found / pull fails | Check the image name and registry access; pull manually with `podman pull <image>` |
