"""agentlib — tiny shared helper for every Python script in this kit.

Resolves AGENT_HOME (env, else the parent of this bin/ directory), the standard sub-directories, and loads
config/agent.env (KEY=VALUE lines) into os.environ WITHOUT overriding values that
are already set in the real environment. Never prints secret values.
"""
import os

# AGENT_HOME: env var if set, else the directory this bin/ lives in (the install root).
AGENT_HOME = os.path.abspath(os.path.expanduser(
    os.environ.get("AGENT_HOME") or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
BIN = os.path.join(AGENT_HOME, "bin")
STATE = os.path.join(AGENT_HOME, "state")
LOGS = os.path.join(AGENT_HOME, "logs")
MEMORY = os.path.join(AGENT_HOME, "memory")
ENV_FILE = os.path.join(AGENT_HOME, "config", "agent.env")


def load_env(path=ENV_FILE):
    """Parse a simple KEY=VALUE file (comments/blank lines ignored, optional quotes)."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if " #" in v and not v.startswith(("'", '"')):
                    v = v.split(" #", 1)[0].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                os.environ.setdefault(k, v)
    except OSError:
        pass


def env(key, default=None):
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def env_int(key, default):
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


def env_float(key, default):
    try:
        return float(env(key, default))
    except (TypeError, ValueError):
        return default


def ensure_dirs():
    for d in (STATE, LOGS, MEMORY):
        os.makedirs(d, exist_ok=True)


def atomic_json(path, obj):
    import json
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


load_env()
