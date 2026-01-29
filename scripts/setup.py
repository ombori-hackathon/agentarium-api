#!/usr/bin/env python3
"""
Agentarium Setup Script

This script installs the Agentarium hook for Claude Code.
It:
1. Creates ~/.agentarium directory
2. Copies hook.sh to ~/.agentarium/hook.sh
3. Updates ~/.claude/settings.json with hook configuration

Usage:
    python scripts/setup.py [--uninstall]
"""

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path


HOOK_CONFIG = {
    "hooks": {
        "SessionStart": [{
            "matcher": "*",
            "hooks": [{"type": "command", "command": "~/.agentarium/hook.sh", "timeout": 5000}]
        }],
        "PreToolUse": [{
            "matcher": "*",
            "hooks": [{"type": "command", "command": "~/.agentarium/hook.sh", "timeout": 5000}]
        }],
        "PostToolUse": [{
            "matcher": "*",
            "hooks": [{"type": "command", "command": "~/.agentarium/hook.sh", "timeout": 5000}]
        }],
        "SessionEnd": [{
            "matcher": "*",
            "hooks": [{"type": "command", "command": "~/.agentarium/hook.sh", "timeout": 5000}]
        }]
    }
}


def get_script_dir() -> Path:
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def install():
    """Install Agentarium hooks for Claude Code."""
    home = Path.home()
    agentarium_dir = home / ".agentarium"
    claude_dir = home / ".claude"
    settings_file = claude_dir / "settings.json"

    print("Installing Agentarium hooks for Claude Code...")
    print()

    # 1. Create ~/.agentarium directory
    agentarium_dir.mkdir(exist_ok=True)
    print(f"  Created {agentarium_dir}")

    # 2. Copy hook.sh
    source_hook = get_script_dir() / "hook.sh"
    dest_hook = agentarium_dir / "hook.sh"

    if source_hook.exists():
        shutil.copy(source_hook, dest_hook)
    else:
        # Fallback: write hook script directly
        hook_content = '''#!/bin/bash
# Agentarium hook for Claude Code
AGENTARIUM_URL="${AGENTARIUM_URL:-http://localhost:8000}"
EVENT_JSON=$(cat)
curl -s -X POST "${AGENTARIUM_URL}/api/events" \\
  -H "Content-Type: application/json" \\
  -d "$EVENT_JSON" > /dev/null 2>&1 &
'''
        dest_hook.write_text(hook_content)

    # Make executable
    dest_hook.chmod(dest_hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  Installed {dest_hook}")

    # 3. Update Claude settings
    claude_dir.mkdir(exist_ok=True)

    settings = {}
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
        except json.JSONDecodeError:
            print(f"  Warning: Could not parse existing {settings_file}")

    # Merge hook configuration
    if "hooks" not in settings:
        settings["hooks"] = {}

    for event_name, event_config in HOOK_CONFIG["hooks"].items():
        settings["hooks"][event_name] = event_config

    # Write updated settings
    settings_file.write_text(json.dumps(settings, indent=2))
    print(f"  Updated {settings_file}")

    print()
    print("Installation complete!")
    print()
    print("To use Agentarium:")
    print("  1. Start the API:    cd services/api && uv run fastapi dev")
    print("  2. Run the client:   cd apps/macos-client && swift run AgentariumClient")
    print("  3. Start Claude Code in any project directory")
    print()


def uninstall():
    """Remove Agentarium hooks from Claude Code."""
    home = Path.home()
    agentarium_dir = home / ".agentarium"
    settings_file = home / ".claude" / "settings.json"

    print("Uninstalling Agentarium hooks...")
    print()

    # Remove hook script
    hook_file = agentarium_dir / "hook.sh"
    if hook_file.exists():
        hook_file.unlink()
        print(f"  Removed {hook_file}")

    # Remove agentarium directory if empty
    if agentarium_dir.exists():
        try:
            agentarium_dir.rmdir()
            print(f"  Removed {agentarium_dir}")
        except OSError:
            print(f"  {agentarium_dir} not empty, skipping removal")

    # Remove hooks from Claude settings
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
            if "hooks" in settings:
                for event_name in HOOK_CONFIG["hooks"]:
                    if event_name in settings["hooks"]:
                        # Remove Agentarium hook entries
                        settings["hooks"][event_name] = [
                            h for h in settings["hooks"][event_name]
                            if not any(
                                hook.get("command", "").endswith("agentarium/hook.sh")
                                for hook in h.get("hooks", [])
                            )
                        ]
                        # Remove empty event entries
                        if not settings["hooks"][event_name]:
                            del settings["hooks"][event_name]

                # Remove hooks key if empty
                if not settings["hooks"]:
                    del settings["hooks"]

                settings_file.write_text(json.dumps(settings, indent=2))
                print(f"  Updated {settings_file}")
        except (json.JSONDecodeError, KeyError):
            pass

    print()
    print("Uninstall complete!")


def main():
    parser = argparse.ArgumentParser(description="Install Agentarium hooks for Claude Code")
    parser.add_argument("--uninstall", action="store_true", help="Remove Agentarium hooks")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
