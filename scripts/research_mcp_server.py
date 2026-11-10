"""Stable stdio entry point for the research-agent MCP server.

Qoder and other clients may launch the process from their own install
directory. This launcher pins both the working directory and the import path
to this repository, so the MCP always serves the design in this folder rather
than a stale copy elsewhere on the machine.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_windows_user_env(names):
    """Read provider key *names* from HKCU\\Environment without logging values.

    Qoder may start the MCP process before the user environment is refreshed;
    this keeps secrets out of project files while still letting the local
    server use the user's configured key.
    """
    if os.name != "nt":
        return
    try:
        import winreg
    except ImportError:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in names:
                if os.environ.get(name):
                    continue
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                if value:
                    os.environ[name] = str(value)
    except OSError:
        return


_load_windows_user_env(
    (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "OPENAI_API_KEY",
        "ZHIPU_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENALEX_API_KEY",
        "OPENALEX_EMAIL",
    )
)

from research_agent.mcp_server import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
