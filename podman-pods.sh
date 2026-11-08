#!/usr/bin/env bash
# podman-pods.sh — interactive manager for podman container definitions.
#
# Keeps pod definitions in podman.pods (INI-style, hand-editable) next to
# this script. From a menu you can run or edit saved pods, create a new
# one, or exit. First run creates the file and walks you through the
# first pod.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PODS_FILE="$SCRIPT_DIR/podman.pods"
PODMAN_BIN="${PODMAN_BIN:-podman}"

# --- state ----------------------------------------------------------------
declare -a POD_NAMES=()
declare -A POD_IMAGE=() POD_PORTS=() POD_VOLUMES=() POD_ENVS=() POD_COMMAND=()

# --- small helpers --------------------------------------------------------
die() { echo "Error: $*" >&2; exit 1; }

# ask VAR "prompt text" [default]
# Prompts and stores the reply in VAR (the default if the reply is empty).
# Exits cleanly on EOF (Ctrl-D).
ask() {
  local __var="$1" text="$2" default="${3:-}" defpart="" reply
  if [ -n "$default" ]; then defpart=" [$default]"; fi
  read -r -p "$text$defpart: " reply || exit 0
  if [ -z "$reply" ]; then reply="$default"; fi
  printf -v "$__var" '%s' "$reply"
}

valid_name()   { [[ "$1" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; }
valid_port()   { [[ "$1" =~ ^[0-9]+(:[0-9]+)?$ ]]; }
valid_volume() { [[ "$1" =~ ^[^:]+:.+$ ]]; }
valid_env()    { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]]; }

pod_in_list() {
  local n="$1" x
  for x in "${POD_NAMES[@]}"; do
    if [ "$x" = "$n" ]; then return 0; fi
  done
  return 1
}

# --- config file ----------------------------------------------------------
load_pods() {
  [ -f "$PODS_FILE" ] || return 0
  local section="" line key value
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^[[:space:]]*(#|$) ]]; then continue; fi
    if [[ "$line" =~ ^\[[^]]+\][[:space:]]*$ ]]; then
      section="${BASH_REMATCH[0]#[}"
      section="${section%]}"
      POD_NAMES+=("$section")
      POD_IMAGE["$section"]=""
      POD_PORTS["$section"]=""
      POD_VOLUMES["$section"]=""
      POD_ENVS["$section"]=""
      POD_COMMAND["$section"]=""
      continue
    fi
    if [[ "$line" =~ ^([a-z]+)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      value="${BASH_REMATCH[2]}"
      if [ -z "$section" ]; then continue; fi
      case "$key" in
        image)   POD_IMAGE["$section"]="$value" ;;
        port)    POD_PORTS["$section"]+="$value"$'\n' ;;
        volume)  POD_VOLUMES["$section"]+="$value"$'\n' ;;
        env)     POD_ENVS["$section"]+="$value"$'\n' ;;
        command) POD_COMMAND["$section"]="$value" ;;
      esac
    fi
  done < "$PODS_FILE"
}

save_pods() {
  local tmp name p v e
  tmp="$(mktemp)"
  {
    echo "# podman.pods — container definitions managed by podman-pods.sh"
    echo "# One [name] section per pod. Hand-editable."
    echo "#   image=    container image (required)"
    echo "#   port=     host:container port mapping (repeatable)"
    echo "#   volume=   host:container volume mount (repeatable)"
    echo "#   env=      KEY=VALUE environment variable (repeatable)"
    echo "#   command=  command to run instead of the image default"
    echo
    for name in "${POD_NAMES[@]}"; do
      echo "[$name]"
      echo "image=${POD_IMAGE[$name]:-}"
      while IFS= read -r p; do
        if [ -n "$p" ]; then echo "port=$p"; fi
      done <<< "${POD_PORTS[$name]:-}"
      while IFS= read -r v; do
        if [ -n "$v" ]; then echo "volume=$v"; fi
      done <<< "${POD_VOLUMES[$name]:-}"
      while IFS= read -r e; do
        if [ -n "$e" ]; then echo "env=$e"; fi
      done <<< "${POD_ENVS[$name]:-}"
      echo "command=${POD_COMMAND[$name]:-}"
      echo
    done
  } > "$tmp"
  mv "$tmp" "$PODS_FILE"
}

# --- the walkthrough ------------------------------------------------------
# edit_list LABEL FORMAT CURRENT VALIDATOR
# Interactive add/remove loop over a newline-separated list.
# Result is stored in EDIT_LIST_RESULT.
edit_list() {
  local label="$1" format="$2" current="$3" validator="$4"
  local items=() item c new idx i
  while IFS= read -r item; do
    if [ -n "$item" ]; then items+=("$item"); fi
  done <<< "$current"

  while true; do
    echo
    echo "Current $label(s):"
    if [ "${#items[@]}" -eq 0 ]; then
      echo "  (none)"
    else
      i=1
      for item in "${items[@]}"; do
        printf "  %d. %s\n" "$i" "$item"
        i=$((i + 1))
      done
    fi
    ask c "Number to remove, 'a' to add, or Enter to finish"
    case "$c" in
      '') break ;;
      a|A)
        ask new "New $label ($format, Enter to cancel)"
        while [ -n "$new" ]; do
          if "$validator" "$new"; then break; fi
          echo "Invalid format (expected $format)."
          ask new "New $label ($format, Enter to cancel)"
        done
        if [ -n "$new" ]; then items+=("$new"); fi
        ;;
      *[!0-9]*) echo "Invalid input." ;;
      *)
        idx=$((10#$c))
        if [ "$idx" -ge 1 ] && [ "$idx" -le "${#items[@]}" ]; then
          echo "Removed: ${items[$((idx - 1))]}"
          items=("${items[@]:0:idx - 1}" "${items[@]:idx}")
        else
          echo "Number out of range."
        fi
        ;;
    esac
  done

  local out=""
  for item in "${items[@]}"; do out+="$item"$'\n'; done
  EDIT_LIST_RESULT="$out"
}

# walk_options NAME
# Prompts for every option of pod NAME (pre-filled if already set) and
# stores the results in the POD_* arrays.
walk_options() {
  local name="$1" image ports volumes envs command
  image="${POD_IMAGE[$name]:-}"
  ports="${POD_PORTS[$name]:-}"
  volumes="${POD_VOLUMES[$name]:-}"
  envs="${POD_ENVS[$name]:-}"
  command="${POD_COMMAND[$name]:-}"

  while true; do
    ask image "Image (e.g. docker.io/library/nginx:latest)" "$image"
    if [ -n "$image" ]; then break; fi
    echo "Image is required."
  done

  edit_list "port mapping" "host:container" "$ports" valid_port
  ports="$EDIT_LIST_RESULT"
  edit_list "volume" "host:container" "$volumes" valid_volume
  volumes="$EDIT_LIST_RESULT"
  edit_list "environment variable" "KEY=VALUE" "$envs" valid_env
  envs="$EDIT_LIST_RESULT"

  ask command "Command to run (optional, overrides image default)" "$command"

  POD_IMAGE["$name"]="$image"
  POD_PORTS["$name"]="$ports"
  POD_VOLUMES["$name"]="$volumes"
  POD_ENVS["$name"]="$envs"
  POD_COMMAND["$name"]="$command"
}

create_pod() {
  echo
  echo "--- Create new pod ---"
  local name
  while true; do
    ask name "Container name"
    if [ -z "$name" ]; then
      echo "Name is required."
    elif ! valid_name "$name"; then
      echo "Invalid name — use letters, numbers, . _ - (start with a letter or number)."
    elif pod_in_list "$name"; then
      echo "A pod named '$name' already exists."
    else
      break
    fi
  done

  walk_options "$name"
  POD_NAMES+=("$name")
  save_pods
  echo
  echo "Pod '$name' saved to $PODS_FILE"
}

edit_pod() {
  local name="$1" newname i
  echo
  echo "--- Edit pod: $name ---"

  ask newname "Container name" "$name"
  if [ "$newname" != "$name" ]; then
    while true; do
      if valid_name "$newname" && ! pod_in_list "$newname"; then break; fi
      echo "Invalid name, or a pod with that name already exists."
      ask newname "Container name" "$name"
    done
    POD_IMAGE["$newname"]="${POD_IMAGE[$name]:-}"
    POD_PORTS["$newname"]="${POD_PORTS[$name]:-}"
    POD_VOLUMES["$newname"]="${POD_VOLUMES[$name]:-}"
    POD_ENVS["$newname"]="${POD_ENVS[$name]:-}"
    POD_COMMAND["$newname"]="${POD_COMMAND[$name]:-}"
    unset "POD_IMAGE[$name]" "POD_PORTS[$name]" "POD_VOLUMES[$name]" "POD_ENVS[$name]" "POD_COMMAND[$name]"
    for i in "${!POD_NAMES[@]}"; do
      if [ "${POD_NAMES[$i]}" = "$name" ]; then
        POD_NAMES["$i"]="$newname"
      fi
    done
    name="$newname"
  fi

  walk_options "$name"
  save_pods
  echo
  echo "Pod '$name' saved to $PODS_FILE"
}

# --- running --------------------------------------------------------------
run_pod() {
  local name="$1"
  if ! command -v "$PODMAN_BIN" >/dev/null 2>&1; then
    die "'$PODMAN_BIN' not found. Install podman, or set PODMAN_BIN to the binary."
  fi

  # If a container with this name already exists, deal with it.
  if "$PODMAN_BIN" container exists "$name" 2>/dev/null; then
    local state c
    state="$("$PODMAN_BIN" inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo unknown)"
    echo "Container '$name' already exists (state: $state)."
    ask c "[s]tart it, [r]emove and recreate, or [c]ancel" "c"
    case "$c" in
      s|S)
        "$PODMAN_BIN" start "$name"
        echo "Started. Follow with: $PODMAN_BIN logs -f $name"
        return 0
        ;;
      r|R)
        "$PODMAN_BIN" rm -f "$name"
        ;;
      *)
        echo "Cancelled."
        return 0
        ;;
    esac
  fi

  local mode
  ask mode "Run in [f]oreground or [d]etached?" "f"
  local args=(run)
  if [ "$mode" = "d" ] || [ "$mode" = "D" ]; then
    args+=(-d)
  else
    args+=(-it)
  fi
  args+=(--name "$name")

  local p v e
  while IFS= read -r p; do
    if [ -n "$p" ]; then args+=(-p "$p"); fi
  done <<< "${POD_PORTS[$name]:-}"
  while IFS= read -r v; do
    if [ -n "$v" ]; then args+=(-v "$v"); fi
  done <<< "${POD_VOLUMES[$name]:-}"
  while IFS= read -r e; do
    if [ -n "$e" ]; then args+=(-e "$e"); fi
  done <<< "${POD_ENVS[$name]:-}"

  args+=("${POD_IMAGE[$name]}")
  if [ -n "${POD_COMMAND[$name]:-}" ]; then
    local cmd_words=()
    read -r -a cmd_words <<< "${POD_COMMAND[$name]}"
    args+=("${cmd_words[@]}")
  fi

  echo
  echo "Running: $PODMAN_BIN ${args[*]}"
  "$PODMAN_BIN" "${args[@]}"
}

# --- menu -----------------------------------------------------------------
show_menu() {
  local i=1 name
  echo
  echo "=== Podman Pods ==="
  for name in "${POD_NAMES[@]}"; do
    printf "  %d. %-20s (%s)\n" "$i" "$name" "${POD_IMAGE[$name]:-}"
    i=$((i + 1))
  done
  printf "  %d. Create new pod\n" "$i"
  printf "  %d. Exit\n" "$((i + 1))"
  echo
}

pod_submenu() {
  local name="$1" c
  while true; do
    echo
    echo "Pod: $name (${POD_IMAGE[$name]:-})"
    echo "  [r]un  [e]dit  [b]ack"
    ask c "Choice"
    case "$c" in
      r|R) run_pod "$name" ;;
      e|E) edit_pod "$name" ;;
      b|B|q|Q) return 0 ;;
      *) echo "Invalid choice." ;;
    esac
  done
}

main() {
  if [ ! -f "$PODS_FILE" ]; then
    save_pods
    echo "Created $PODS_FILE"
    create_pod
  else
    load_pods
  fi

  if ! command -v "$PODMAN_BIN" >/dev/null 2>&1; then
    echo "Warning: podman is not installed (looked for '$PODMAN_BIN')." >&2
    echo "You can still create and edit pod definitions, but 'run' will not work until podman is installed." >&2
  fi

  local n choice sel
  while true; do
    n=${#POD_NAMES[@]}
    show_menu
    ask choice "Choose an option"
    case "$choice" in
      ''|*[!0-9]*) echo "Invalid choice." ;;
      *)
        sel=$((10#$choice))
        if [ "$sel" -ge 1 ] && [ "$sel" -le "$n" ]; then
          pod_submenu "${POD_NAMES[$((sel - 1))]}"
        elif [ "$sel" -eq $((n + 1)) ]; then
          create_pod
        elif [ "$sel" -eq $((n + 2)) ]; then
          exit 0
        else
          echo "Invalid choice."
        fi
        ;;
    esac
  done
}

main "$@"
