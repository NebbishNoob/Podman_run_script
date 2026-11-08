Container Stack & Pod Managers


A pair of zero-dependency Python CLI tools built for Linux systems running Podman (or Docker). They provide interactive terminal menus to construct, tune, and control containerized workloads without requiring complex manual command string composition.

🛠️ Included Tools
Tool	Config Target	Description
composer.py	docker-compose.yml	Multi-service stack composer and lifecycle manager with automatic volume path handling and shell attachments.
pods.py	podman.pods	Individual container definition and engine manager backed by an INI-style persistent config file.
🚀 Key Features
Zero External Python Dependencies: Built strictly using native Python standard libraries (urllib, json, configparser, subprocess, re).

Docker Hub Search Integration: Query the Docker Hub v2 API directly inside the CLI walkthrough to select images, view star counts, and identify official repositories.

Auto-Provisioning Volume Directories: Pre-checks and creates local volume target paths (./containers/<service_name>/data) to prevent statfs host directory errors prior to container launch.

Interactive TTY Shell Access: One-key terminal attachment to running containers using auto-fallback from bash to standard /bin/sh for minimal distros like Alpine.

Multi-Engine Detection: Automatically detects available system engines across podman-compose, podman compose, and standard docker compose.

Config Security Hardening: Restricts permissions (chmod 0600) on generated configuration files (docker-compose.yml, podman.pods) and strips control characters from API searches.

📦 Requirements
Python 3.6+

Podman (v4.0+) or Docker

podman-compose (optional, for compose multi-container management)

💻 Quick Start
Make the scripts executable and launch either tool:

Bash
chmod +x composer.py pods.py

# Manage compose stacks
./composer.py

# Manage individual podman container definitions
./pods.py
📁 Project Directory Structure
Plaintext
.
├── composer.py         # Multi-service compose stack manager
├── pods.py             # Single container definition manager
├── docker-compose.yml  # Managed compose stack file (auto-generated)
├── podman.pods         # Managed INI pod definitions (auto-generated)
└── containers/         # Default isolated host directories for volumes
    ├── service_a/
    │   └── data/
    └── service_b/
        └── data/
📖 Usage Overview
composer.py — Docker/Podman Compose Manager
Service Walkthrough: Prompt-driven setup for Service Name, Image (with inline Docker Hub search), Port Mappings (8080:80), Volume Mounts, Environment Variables (KEY=VALUE), and Restart Policies.

Stack Control Menu:

Global lifecycle: [u]p (detached), [d]own, [l]ogs, [p]s.

Individual container actions: Start, Stop, Tail Logs, Attach TTY Shell.

Persisted Configuration: Serializes valid Docker Compose YAML configurations formatted with standard version: '3.8' definitions.

pods.py — Podman Container Manager
INI Definition File (podman.pods): Saves container configurations cleanly into flat INI sections for fast manual editing or script walkthroughs.

Container Browser: Lists all active and stopped system containers (podman ps -a) with real-time state inspects.

Quiet Shell Attach: Silently detects /bin/bash availability inside target containers and falls back to /bin/sh without throwing OCI runtime errors.
