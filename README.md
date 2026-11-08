# Podman_run_script

Utility scripts for everyday terminal work. Plain bash, no dependencies
beyond standard Linux tools.

Currently contains:

- [pods](#pods) — interactive manager for podman container definitions

## Setup

Make the scripts executable (already done, but re-run if you copy them):

```bash
chmod +x ~/projects/scripts/pods
```

Optionally add the directory to your `PATH` so you can run them from anywhere:

```bash
echo 'export PATH="$HOME/projects/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

After that, `pods` works from any directory. Without the `PATH`
change, run it as `./pods` from inside this folder.

---

## pods

Interactive manager for podman container definitions. Keeps everything in
`podman.pods` (INI-style, hand-editable) in the script's own folder.

```
Usage: pods
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
  3. Show containers
  4. Create new pod
  5. Exit
```

Pick a pod to get a sub-menu:

```
Pod: myweb (docker.io/library/nginx:latest)
  [r]un  [e]dit  [b]ack
```

The last three options are always "Show containers", "Create new pod",
and "Exit", numbered after the pods.

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
updated). After saving, you're returned to the main menu.

### Containers

The **Show containers** option lists every running podman container on the
system (not just the pods in `podman.pods`) with name, image, status, and
ports. Stopped (exited) containers are listed below for reference.

Select a running container to get a sub-menu:

```
Container: myweb
  [s]top  [h]ell (open shell)  [b]ack
```

- **s** — stops the container (`podman stop`)
- **h** — opens a shell inside it (`podman exec -it`). The script probes
  for `/bin/bash` first and falls back to `/bin/sh`, so minimal images
  like alpine work. Type `exit` in the container to leave.

Press Enter at the container list to go back to the main menu.

### Running a pod

If a container with the pod's name already exists, you're offered:

- **s** — start it (then follow with `podman logs -f <name>`)
- **r** — remove and recreate it
- **c** — cancel

Otherwise you choose **foreground** (`-it`, Enter) or **detached** (`d`,
`-d`). The exact `podman run` command is printed before it runs.

If a podman command fails (pull error, port in use, ...), the error is
shown and you're returned to the menu — the script itself never exits
because of a failed run.

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
  `PODMAN_BIN=/usr/local/bin/podman ./pods`
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
