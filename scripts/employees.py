#!/usr/bin/env python3
"""
Register, list, and remove employees.

Registering means storing one person's TimeTrack token against their Slack user
id. To get a token: sign in to TimeTrack, open DevTools -> Network, click any
action, and copy the value after `Bearer ` in the Authorization header.

    python scripts/employees.py add    --slack-id U04TQ9XKMLR --label ada
    python scripts/employees.py list
    python scripts/employees.py remove --slack-id U04TQ9XKMLR
    python scripts/employees.py check  --slack-id U04TQ9XKMLR

`add` prompts for the token rather than taking it as an argument, so it never
lands in your shell history.
"""
import argparse
import asyncio
import base64
import getpass
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.store import delete_employee, get_token, init_db, list_employees, put_token  # noqa: E402
from app.timetrack import TimeTrackClient, TimeTrackError, is_clocked_in  # noqa: E402


def describe_token(token: str) -> str:
    """Reads the expiry out of a JWT without verifying it, for a friendly warning."""
    try:
        payload_segment = token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return "could not read token claims (is this a JWT?)"

    parts = []
    if "email" in claims:
        parts.append(str(claims["email"]))
    if "exp" in claims:
        expires = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        remaining = expires - datetime.now(timezone.utc)
        days = remaining.days
        if remaining.total_seconds() < 0:
            parts.append(f"EXPIRED on {expires:%Y-%m-%d %H:%M UTC}")
        else:
            parts.append(f"expires {expires:%Y-%m-%d %H:%M UTC} ({days}d away)")
    else:
        parts.append("no expiry claim found")
    return "; ".join(parts)


def cmd_add(args: argparse.Namespace) -> int:
    token = getpass.getpass("Paste the TimeTrack token (input hidden): ").strip()
    if not token:
        print("No token entered.", file=sys.stderr)
        return 1

    print(f"Token: {describe_token(token)}")
    put_token(args.slack_id, token, args.label)
    print(f"Registered {args.slack_id}" + (f" ({args.label})" if args.label else ""))
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    rows = list_employees()
    if not rows:
        print("No employees registered.")
        return 0
    for row in rows:
        print(f"{row['slack_user_id']}\t{row['label'] or ''}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    if delete_employee(args.slack_id):
        print(f"Removed {args.slack_id}")
        return 0
    print(f"No such employee: {args.slack_id}", file=sys.stderr)
    return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Calls TimeTrack with the stored token to confirm it still works."""
    token = get_token(args.slack_id)
    if not token:
        print(f"No such employee: {args.slack_id}", file=sys.stderr)
        return 1

    print(f"Token: {describe_token(token)}")

    async def run() -> int:
        try:
            today = await TimeTrackClient(token).today()
        except TimeTrackError as exc:
            print(f"TimeTrack call failed: {exc}", file=sys.stderr)
            return 1
        print(f"today -> {json.dumps(today, indent=2, default=str)}")
        print(f"interpreted as clocked_in={is_clocked_in(today)}")
        return 0

    return asyncio.run(run())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="register an employee (prompts for the token)")
    add.add_argument("--slack-id", required=True, help="Slack member ID, e.g. U04TQ9XKMLR")
    add.add_argument("--label", help="a name, for your own reference")
    add.set_defaults(func=cmd_add)

    sub.add_parser("list", help="list registered employees").set_defaults(func=cmd_list)

    remove = sub.add_parser("remove", help="remove an employee")
    remove.add_argument("--slack-id", required=True)
    remove.set_defaults(func=cmd_remove)

    check = sub.add_parser("check", help="verify a stored token against TimeTrack")
    check.add_argument("--slack-id", required=True)
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
