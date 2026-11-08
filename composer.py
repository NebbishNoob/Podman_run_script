#!/usr/bin/env python3
"""composer.py — Interactive CLI manager for Docker/Podman Compose stacks."""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

COMPOSE_FILE = "docker-compose.yml"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTAINERS_DIR = os.path.join(SCRIPT_DIR, "containers")


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
    """Set strict read/write permissions (0600) on config files."""
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
    """Require host:container mapping (e.g. 8080:80 or 53:53/udp)."""
    return bool(re.match(r"^[0-9]+:[0-9]+(/udp|/tcp)?$", port))


def validate_volume(vol: str, service_name: str = "") -> bool:
    """Ensure target path is valid and create missing host paths automatically."""
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
    req = urllib.request.Request(url, headers={"User-Agent": "ComposerCLI/1.0"})

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


def get_compose_engine() -> list:
    """Detect available compose executable (podman-compose, podman compose, docker compose)."""
    if shutil.which("podman-compose"):
        return ["podman-compose"]
    if shutil.which("podman"):
        return ["podman", "compose"]
    if shutil.which("docker"):
        return ["docker", "compose"]
    return []


def run_compose_cmd(args: list):
    engine = get_compose_engine()
    if not engine:
        print("Error: Neither 'podman-compose', 'podman', nor 'docker' found in PATH.", file=sys.stderr)
        return

    cmd = engine + ["-f", COMPOSE_FILE] + args
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"Failed to run compose command: {e}", file=sys.stderr)


def attach_container_shell(service_name: str):
    """Attach interactive bash/sh TTY shell to a running container."""
    engine = get_compose_engine()
    if not engine:
        print("Error: No engine found.", file=sys.stderr)
        return

    print(f"Attempting shell attachment to '{service_name}'...")
    # Try bash first, fallback to sh if bash is unavailable
    bash_cmd = engine + ["-f", COMPOSE_FILE, "exec", service_name, "bash"]
    sh_cmd = engine + ["-f", COMPOSE_FILE, "exec", service_name, "sh"]

    res = subprocess.run(bash_cmd, check=False)
    if res.returncode != 0:
        subprocess.run(sh_cmd, check=False)


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


class ComposeManager:
    def __init__(self, filepath: str = COMPOSE_FILE):
        self.filepath = filepath
        self.services = {}
        ensure_dir(CONTAINERS_DIR)
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            return

        current_svc = None
        current_key = None

        with open(self.filepath, "r") as f:
            for line in f:
                line_str = line.rstrip()
                if not line_str or line_str.lstrip().startswith("#"):
                    continue

                svc_match = re.match(r"^ {2}([a-zA-Z0-9._-]+):$", line_str)
                if svc_match:
                    current_svc = svc_match.group(1)
                    self.services[current_svc] = {
                        "image": "",
                        "restart": "unless-stopped",
                        "command": "",
                        "ports": [],
                        "volumes": [],
                        "environment": [],
                    }
                    current_key = None
                    continue

                if not current_svc:
                    continue

                attr_match = re.match(r"^ {4}([a-z_]+):\s*(.*)$", line_str)
                if attr_match:
                    k, v = attr_match.group(1), attr_match.group(2).strip("\"'")
                    if k in ("image", "restart", "command"):
                        self.services[current_svc][k] = v
                        current_key = None
                    elif k in ("ports", "volumes", "environment"):
                        current_key = k
                    continue

                list_match = re.match(r"^ {6}-\s*\"?(.*?)\"?$", line_str)
                if list_match and current_key:
                    self.services[current_svc][current_key].append(list_match.group(1))

    def save(self):
        lines = [
            "# Generated by composer.py — interactive Docker Compose manager",
            "version: '3.8'",
            "",
            "services:",
        ]
        for name, config in self.services.items():
            lines.append(f"  {name}:")
            lines.append(f"    container_name: {name}")
            lines.append(f"    image: {config.get('image', '')}")
            lines.append(f"    restart: {config.get('restart', 'unless-stopped')}")
            lines.append("    tty: true")
            lines.append("    stdin_open: true")

            if config.get("command"):
                lines.append(f"    command: {config['command']}")

            for key in ("ports", "volumes", "environment"):
                if config.get(key):
                    lines.append(f"    {key}:")
                    for item in config[key]:
                        lines.append(f'      - "{item}"')
                        if key == "volumes":
                            host_path = item.split(":", 1)[0]
                            ensure_dir(host_path)
            lines.append("")

        with open(self.filepath, "w") as f:
            f.write("\n".join(lines))
        secure_file_perms(self.filepath)

    def walk_service_options(self, name: str):
        svc = self.services.get(
            name,
            {
                "image": "",
                "restart": "unless-stopped",
                "command": "",
                "ports": [],
                "volumes": [],
                "environment": [],
            },
        )

        image = svc.get("image", "")
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

        svc["image"] = image
        svc["ports"] = edit_list("port mapping", svc.get("ports", []), validate_port, "host:container e.g. 8080:80")

        # Default volume suggestion inside container's isolated subdirectory
        default_vol = f"./containers/{name}/data:/data"
        svc["volumes"] = edit_list(
            "volume mount",
            svc.get("volumes", []),
            lambda v: validate_volume(v, name),
            "host:container e.g. ./containers/app/data:/data",
            default_suggestion=default_vol,
        )

        svc["environment"] = edit_list("environment variable", svc.get("environment", []), validate_env, "KEY=VALUE")
        svc["command"] = ask("Command to run (optional)", svc.get("command", ""))
        svc["restart"] = ask("Restart policy (no/always/on-failure/unless-stopped)", svc.get("restart", "unless-stopped"))

        self.services[name] = svc
        self.save()

    def create_service(self):
        print("\n--- Create New Service ---")
        while True:
            name = ask("Service name")
            if not name:
                print("Name is required.")
            elif not validate_name(name):
                print("Invalid name (use alphanumeric, dots, underscores, hyphens).")
            elif name in self.services:
                print(f"Service '{name}' already exists.")
            else:
                break

        # Pre-create container directory
        ensure_dir(os.path.join(CONTAINERS_DIR, name))
        self.walk_service_options(name)

    def delete_service(self, name: str):
        """Remove a service configuration and optionally clean up host directories."""
        if name not in self.services:
            return

        confirm = ask(f"Are you sure you want to remove service '{name}' from compose file? [y/N]", "n").lower()
        if confirm == "y":
            run_compose_cmd(["stop", name])
            run_compose_cmd(["rm", "-f", name])
            del self.services[name]
            self.save()
            print(f"Service '{name}' deleted.")

            clean_dir = ask(f"Delete isolated host folder './containers/{name}' as well? [y/N]", "n").lower()
            if clean_dir == "y":
                target_dir = os.path.join(CONTAINERS_DIR, name)
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir, ignore_errors=True)
                    print(f" Removed {target_dir}")


def service_submenu(manager: ComposeManager, name: str):
    """Individual service action menu."""
    while True:
        img = manager.services[name].get("image", "")
        print(f"\nService: {name} ({img})")
        print("  [s]tart      [t]op/stop   [l]ogs       [e]xec shell")
        print("  [m]odify     [d]elete     [b]ack")

        choice = ask("Choice").lower()
        if choice == "s":
            run_compose_cmd(["up", "-d", name])
        elif choice == "t":
            run_compose_cmd(["stop", name])
        elif choice == "l":
            run_compose_cmd(["logs", "-f", name])
        elif choice == "e":
            attach_container_shell(name)
        elif choice == "m":
            manager.walk_service_options(name)
        elif choice == "d":
            manager.delete_service(name)
            break
        elif choice in ("b", "q"):
            break


def stack_menu(manager: ComposeManager):
    """Global stack control menu."""
    while True:
        print(f"\n=== Stack Management ({COMPOSE_FILE}) ===")
        print("  Global:     [u]p (start all)   [d]own (stop & remove)   [l]ogs   [p]s")
        print("  Individual: [s]tart service    [t]op/stop service       [o]logs service   [e]xec shell")
        print("  [b]ack")

        c = ask("Choice").lower()
        if c == "u":
            run_compose_cmd(["up", "-d"])
        elif c == "d":
            run_compose_cmd(["down"])
        elif c == "l":
            run_compose_cmd(["logs", "-f"])
        elif c == "p":
            run_compose_cmd(["ps"])
        elif c in ("s", "t", "o", "e"):
            services = list(manager.services.keys())
            if not services:
                print("No services configured.")
                continue
            print("\nSelect a service:")
            for i, name in enumerate(services, 1):
                print(f"  {i}. {name}")
            sel = ask("Service number")
            if sel.isdigit() and 1 <= int(sel) <= len(services):
                target = services[int(sel) - 1]
                if c == "s":
                    run_compose_cmd(["up", "-d", target])
                elif c == "t":
                    run_compose_cmd(["stop", target])
                elif c == "o":
                    run_compose_cmd(["logs", "-f", target])
                elif c == "e":
                    attach_container_shell(target)
        elif c in ("b", "q"):
            break


def main():
    manager = ComposeManager()

    if not manager.services and not os.path.exists(COMPOSE_FILE):
        print(f"No {COMPOSE_FILE} found. Let's create your first service.")
        manager.create_service()

    while True:
        services = list(manager.services.keys())
        print("\n=== Compose Services ===")
        if not services:
            print("  (no services defined)")
        else:
            for i, name in enumerate(services, 1):
                img = manager.services[name].get("image", "")
                print(f"  {i}. {name:<20} ({img})")

        idx_stack = len(services) + 1
        idx_add = len(services) + 2
        idx_exit = len(services) + 3

        print(f"  {idx_stack}. Stack Control (up/down/logs)")
        print(f"  {idx_add}. Add new service")
        print(f"  {idx_exit}. Exit\n")

        choice = ask("Choose an option")
        if choice.isdigit():
            sel = int(choice)
            if 1 <= sel <= len(services):
                service_submenu(manager, services[sel - 1])
            elif sel == idx_stack:
                stack_menu(manager)
            elif sel == idx_add:
                manager.create_service()
            elif sel == idx_exit:
                sys.exit(0)
            else:
                print("Invalid choice.")
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
