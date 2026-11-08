#!/usr/bin/env python3
"""pods.py — Interactive CLI manager for Podman container definitions."""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PODS_FILE = os.path.join(SCRIPT_DIR, "podman.pods")
CONTAINERS_DIR = os.path.join(SCRIPT_DIR, "containers")
PODMAN_BIN = os.environ.get("PODMAN_BIN") or shutil.which("podman") or "podman"


def ensure_dir(path: str) -> None:
    """Ensure host directory exists to prevent statfs volume mount failures."""
    expanded_path = os.path.expanduser(path)
    if not os.path.isabs(expanded_path):
        expanded_path = os.path.abspath(os.path.join(SCRIPT_DIR, expanded_path))

    if not os.path.exists(expanded_path):
        try:
            os.makedirs(expanded_path, exist_ok=True)
            print(f" Created missing host directory: {expanded_path}")
        except Exception as e:
            print(f" Warning: Could not create directory {expanded_path}: {e}", file=sys.stderr)


def secure_file_perms(filepath: str) -> None:
    """Set strict read/write permissions (0600) on config file."""
    if os.path.exists(filepath):
        try:
            os.chmod(filepath, 0o600)
        except OSError:
            pass


def ask(prompt: str, default: str = "") -> str:
    def_part = f" [{default}]" if default else ""
    try:
        reply = input(f"{prompt}{def_part}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(0)
    return reply if reply else default


def validate_name(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", name))


def validate_port(port: str) -> bool:
    return bool(re.match(r"^[0-9]+(:[0-9]+)?(/udp|/tcp)?$", port))


def validate_volume(vol: str) -> bool:
    if not re.match(r"^[^:]+:.+$", vol):
        return False
    host_path, target_path = vol.split(":", 1)
    if target_path.strip() == "/":
        print(" Error: Cannot mount over container root '/' directory.")
        return False
    ensure_dir(host_path)
    return True


def validate_env(env: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", env))


def search_docker_hub() -> str:
    term = ask("Search Docker Hub for")
    if not term:
        return ""

    encoded = urllib.parse.quote(term)
    url = f"https://hub.docker.com/v2/search/repositories/?query={encoded}&page_size=10"
    req = urllib.request.Request(url, headers={"User-Agent": "PodsCLI/1.0"})

    print("Searching Docker Hub...")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error querying Docker Hub: {e}", file=sys.stderr)
        return ""

    results = data.get("results", [])
    if not results:
        print(f"No results found for '{term}'.")
        return ""

    print(f"\n=== Docker Hub Results for '{term}' ===")
    for i, item in enumerate(results, 1):
        name = item.get("repo_name", "")
        stars = item.get("star_count", 0)
        is_official = item.get("is_official", False)
        desc = item.get("short_description", "").replace("\n", " ")[:60]

        name = "".join(c for c in name if c.isprintable())
        desc = "".join(c for c in desc if c.isprintable())
        badge = " [OFFICIAL]" if is_official else ""

        print(f"  {i:2d}. {name:<30} ⭐ {stars:<5}{badge}\n      {desc}")

    sel = ask("\nSelect image number, or Enter to cancel")
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(results):
            return results[idx].get("repo_name", "")
    return ""


def edit_list(label: str, items: list, validator=None, example_fmt: str = "", default_suggestion: str = "") -> list:
    items = list(items)
    while True:
        print(f"\nCurrent {label}(s):")
        if not items:
            print("  (none)")
        else:
            for i, item in enumerate(items, 1):
                print(f"  {i}. {item}")

        prompt_msg = "Number to remove, 'a' to add"
        if default_suggestion and not items:
            prompt_msg += ", 'd' to add suggested default"
        prompt_msg += ", or Enter to finish"

        choice = ask(prompt_msg).lower()
        if not choice:
            break
        elif choice == "d" and default_suggestion and not items:
            if validator and not validator(default_suggestion):
                print("Failed to validate suggested path.")
            else:
                items.append(default_suggestion)
        elif choice == "a":
            prompt_input = f"New {label}" + (f" ({example_fmt})" if example_fmt else "")
            new_val = ask(prompt_input, default_suggestion if (default_suggestion and not items) else "")
            if new_val:
                if validator and not validator(new_val):
                    print(f"Invalid format. Expected format: {example_fmt}")
                else:
                    items.append(new_val)
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                removed = items.pop(idx)
                print(f"Removed: {removed}")
            else:
                print("Number out of range.")
    return items


class PodManager:
    def __init__(self, filepath: str = PODS_FILE):
        self.filepath = filepath
        self.pods = {}
        ensure_dir(CONTAINERS_DIR)
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            return

        secure_file_perms(self.filepath)
        current_pod = None
        with open(self.filepath, "r") as f:
            for line in f:
                line_str = line.rstrip()
                if not line_str or line_str.lstrip().startswith("#"):
                    continue

                sec_match = re.match(r"^\[(.*?)\]$", line_str)
                if sec_match:
                    current_pod = sec_match.group(1)
                    self.pods[current_pod] = {
                        "image": "",
                        "command": "",
                        "ports": [],
                        "volumes": [],
                        "envs": [],
                    }
                    continue

                if current_pod and "=" in line_str:
                    key, val = line_str.split("=", 1)
                    key, val = key.strip(), val.strip()
                    if key == "image":
                        self.pods[current_pod]["image"] = val
                    elif key == "command":
                        self.pods[current_pod]["command"] = val
                    elif key == "port":
                        self.pods[current_pod]["ports"].append(val)
                    elif key == "volume":
                        self.pods[current_pod]["volumes"].append(val)
                    elif key == "env":
                        self.pods[current_pod]["envs"].append(val)

    def save(self):
        tmp_file = self.filepath + ".tmp"
        lines = [
            "# podman.pods — container definitions managed by pods.py",
            "# One [name] section per pod. Hand-editable.",
            "",
        ]
        for name, data in self.pods.items():
            lines.append(f"[{name}]")
            lines.append(f"image={data.get('image', '')}")
            for p in data.get("ports", []):
                lines.append(f"port={p}")
            for v in data.get("volumes", []):
                lines.append(f"volume={v}")
                host_path = v.split(":", 1)[0]
                ensure_dir(host_path)
            for e in data.get("envs", []):
                lines.append(f"env={e}")
            lines.append(f"command={data.get('command', '')}")
            lines.append("")

        with open(tmp_file, "w") as f:
            f.write("\n".join(lines))

        secure_file_perms(tmp_file)
        os.replace(tmp_file, self.filepath)
        secure_file_perms(self.filepath)

    def walk_options(self, name: str):
        pod = self.pods.get(
            name,
            {"image": "", "command": "", "ports": [], "volumes": [], "envs": []},
        )

        image = pod.get("image", "")
        while True:
            print(f"\nImage: {image or '(none)'}")
            choice = ask("Image name, 's' to search Docker Hub, or Enter to accept", image)
            if choice.lower() == "s":
                searched = search_docker_hub()
                if searched:
                    image = searched
                continue
            if choice:
                image = choice
                break
            print("Image is required.")

        pod["image"] = image
        pod["ports"] = edit_list("port mapping", pod.get("ports", []), validate_port, "host:container e.g. 8080:80")

        default_vol = f"./containers/{name}/data:/data"
        pod["volumes"] = edit_list(
            "volume mount",
            pod.get("volumes", []),
            validate_volume,
            "host:container e.g. ./containers/app/data:/data",
            default_suggestion=default_vol,
        )

        pod["envs"] = edit_list("environment variable", pod.get("envs", []), validate_env, "KEY=VALUE")
        pod["command"] = ask("Command to run (optional, overrides image default)", pod.get("command", ""))

        self.pods[name] = pod
        self.save()

    def create_pod(self):
        print("\n--- Create New Pod Definition ---")
        while True:
            name = ask("Container name")
            if not name:
                print("Name is required.")
            elif not validate_name(name):
                print("Invalid name (letters, numbers, . _ -).")
            elif name in self.pods:
                print(f"A pod named '{name}' already exists.")
            else:
                break

        ensure_dir(os.path.join(CONTAINERS_DIR, name))
        self.walk_options(name)

    def run_pod(self, name: str):
        if not shutil.which(PODMAN_BIN):
            print(f"Cannot run: '{PODMAN_BIN}' not found in PATH.", file=sys.stderr)
            return

        inspect_cmd = [PODMAN_BIN, "inspect", "--format", "{{.State.Status}}", name]
        res = subprocess.run(inspect_cmd, capture_output=True, text=True)

        if res.returncode == 0:
            state = res.stdout.strip()
            print(f"Container '{name}' already exists (state: {state}).")
            c = ask("[s]tart it, [r]emove and recreate, or [c]ancel", "c").lower()
            if c == "s":
                subprocess.run([PODMAN_BIN, "start", name])
                return
            elif c == "r":
                subprocess.run([PODMAN_BIN, "rm", "-f", name])
            else:
                print("Cancelled.")
                return

        pod = self.pods[name]
        mode = ask("Run in [f]oreground or [d]etached?", "d").lower()

        cmd = [PODMAN_BIN, "run"]
        if mode == "d":
            cmd.append("-d")
        else:
            cmd.extend(["-it"])

        cmd.extend(["-i", "--tty", "--restart", "always", "--name", name])

        for p in pod.get("ports", []):
            cmd.extend(["-p", p])
        for v in pod.get("volumes", []):
            host_p = v.split(":", 1)[0]
            ensure_dir(host_p)
            cmd.extend(["-v", v])
        for e in pod.get("envs", []):
            cmd.extend(["-e", e])

        cmd.append(pod["image"])

        if pod.get("command"):
            cmd.extend(pod["command"].split())

        print(f"\nRunning: {' '.join(cmd)}")
        subprocess.run(cmd)


def attach_shell(name: str):
    """Attach interactive shell to running podman container without stderr noise."""
    print(f"Attaching shell to '{name}'...")
    check_bash = [PODMAN_BIN, "exec", name, "test", "-x", "/bin/bash"]
    res = subprocess.run(check_bash, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    shell = "/bin/bash" if res.returncode == 0 else "/bin/sh"
    subprocess.run([PODMAN_BIN, "exec", "-it", name, shell])


def containers_browser(manager: PodManager):
    """View and manage all active/exited podman containers."""
    if not shutil.which(PODMAN_BIN):
        print(f"Error: '{PODMAN_BIN}' not found.", file=sys.stderr)
        return

    while True:
        ps_cmd = [PODMAN_BIN, "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Ports}}"]
        res = subprocess.run(ps_cmd, capture_output=True, text=True)

        containers = []
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    containers.append({"name": parts[0], "image": parts[1], "state": parts[2]})

        print("\n=== All Containers ===")
        if not containers:
            print("No containers found.")
            return

        for i, c in enumerate(containers, 1):
            print(f"  {i}. {c['name']:<20} ({c['image']}) [{c['state']}]")

        choice = ask("\nSelect a container number, or Enter to go back")
        if not choice:
            break

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(containers):
                target = containers[idx]
                container_action_menu(manager, target["name"], target["state"])


def container_action_menu(manager: PodManager, name: str, state: str):
    while True:
        print(f"\nContainer: {name} (status: {state})")
        print("  Actions: ", end="")
        if state == "running":
            print("[t]op/stop  s[h]ell  ", end="")
        else:
            print("[s]tart  ", end="")
        print("[d]elete  ", end="")
        if name in manager.pods:
            print("[e]dit def  ", end="")
        print("[b]ack")

        choice = ask("Choice").lower()
        if choice == "s":
            subprocess.run([PODMAN_BIN, "start", name])
            break
        elif choice == "t":
            subprocess.run([PODMAN_BIN, "stop", name])
            break
        elif choice == "h":
            if state != "running":
                print("Container is not running.")
            else:
                attach_shell(name)
        elif choice == "d":
            confirm = ask(f"Are you sure you want to delete container '{name}'? [y/N]", "n").lower()
            if confirm == "y":
                subprocess.run([PODMAN_BIN, "rm", "-f", name])
                break
        elif choice == "e":
            if name in manager.pods:
                manager.walk_options(name)
                break
            else:
                print("No pod definition saved for this container.")
        elif choice in ("b", "q"):
            break


def pod_submenu(manager: PodManager, name: str):
    while True:
        img = manager.pods[name].get("image", "")
        print(f"\nPod Definition: {name} ({img})")
        print("  [r]un       [e]dit      [d]elete def  [b]ack")
        choice = ask("Choice").lower()

        if choice == "r":
            manager.run_pod(name)
        elif choice == "e":
            manager.walk_options(name)
        elif choice == "d":
            confirm = ask(f"Delete pod definition '{name}' from podman.pods? [y/N]", "n").lower()
            if confirm == "y":
                del manager.pods[name]
                manager.save()
                print(f"Pod definition '{name}' removed.")
                break
        elif choice in ("b", "q"):
            break


def main():
    manager = PodManager()

    if not manager.pods and not os.path.exists(PODS_FILE):
        print(f"No {PODS_FILE} found. Let's create your first pod definition.")
        manager.create_pod()

    while True:
        pod_names = list(manager.pods.keys())
        print("\n=== Podman Pods ===")
        for i, name in enumerate(pod_names, 1):
            img = manager.pods[name].get("image", "")
            print(f"  {i}. {name:<20} ({img})")

        idx_all = len(pod_names) + 1
        idx_add = len(pod_names) + 2
        idx_exit = len(pod_names) + 3

        print(f"  {idx_all}. Show all containers")
        print(f"  {idx_add}. Create new pod definition")
        print(f"  {idx_exit}. Exit\n")

        choice = ask("Choose an option")
        if choice.isdigit():
            sel = int(choice)
            if 1 <= sel <= len(pod_names):
                pod_submenu(manager, pod_names[sel - 1])
            elif sel == idx_all:
                containers_browser(manager)
            elif sel == idx_add:
                manager.create_pod()
            elif sel == idx_exit:
                sys.exit(0)
            else:
                print("Invalid choice.")
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
