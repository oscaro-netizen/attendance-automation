# Attendance Automation

Post a daily start report in Slack → you get clocked in on
[TimeTrack](https://time.marsos.io). Post a completed-work report → you get
clocked out.

That's the whole product.

## How it works

```
Slack message
   ↓  verify signature
   ↓  is it a start report or a completed-work report?
   ↓  look up this person's TimeTrack token
   ↓  GET  /api/attendance/today      (already in that state? stop)
   ↓  POST /api/attendance/clock-in   (or clock-out)
  done
```

No browser automation, no task queue, no attendance records of our own.
TimeTrack already records attendance — it is the system of record, and its
`today` endpoint is what stops a redelivered Slack event clocking you in twice.

The service never posts to Slack, so it needs no bot token and no `chat:write`
scope — only the signing secret used to verify incoming webhooks.

## What triggers what

| Slack message | Result |
|---|---|
| A report containing `- Start`, `Tasks:` and `Expected Today:` | Clock in |
| A report with a line starting `Completed Work` | Clock out |
| Anything else | Ignored |

The `Completed Work` marker must start a line, so writing "I completed work on
the export" in ordinary chat does not clock you out. Slack formatting makes no
difference — a bolded `*Completed Work:*` behaves the same.

## Setup

```bash
cp .env.example .env          # then fill in SLACK_SIGNING_SECRET
docker compose up -d --build
curl localhost:8000/health
```

Point your Slack app's **Event Subscriptions → Request URL** at
`https://<host>/slack/events` and subscribe to `message.channels`
(and `message.im` if you want commands to work in DMs).

## Registering an employee

Each person supplies their own TimeTrack token, which is what authorises the
service to clock them in and out.

To get one: sign in to TimeTrack, open DevTools → **Network**, click any button,
select the request, and copy the value after `Bearer ` in the `Authorization`
header.

```bash
python scripts/employees.py add --slack-id U04TQ9XKMLR --label ada
# prompts for the token (hidden input, so it stays out of shell history)
```

The Slack member ID is on their Slack profile under ⋮ → *Copy member ID*. It
starts with `U`, and is not their display name.

Other commands:

```bash
python scripts/employees.py list
python scripts/employees.py check  --slack-id U04TQ9XKMLR   # is the token still good?
python scripts/employees.py remove --slack-id U04TQ9XKMLR
```

`check` prints the token's expiry and calls TimeTrack with it, which is the
fastest way to confirm someone is set up correctly.

## When a token expires

TimeTrack rejects it, the service logs
`TimeTrack rejected the token; it needs re-registering`, and that person's
clock-ins stop working. Fix: run `add` again with a fresh token — it replaces
the old one.

Nothing is posted to Slack, so **failures are silent to the employee.** Watch
`docker compose logs -f app` if something seems wrong.

## Tests

```bash
python -m pytest -q
```

## Layout

```
app/
  main.py          webhook route, filtering, and the TimeTrack action
  config.py        settings
  slack_verify.py  HMAC signature verification
  messages.py      what counts as a start or completed-work report
  timetrack.py     TimeTrack API client
  store.py         Slack user -> token mapping (SQLite)
scripts/
  employees.py     register / list / check / remove
```

## Notes

- The token database (`data/employees.db`) holds bearer credentials. It is
  chmod `600` and git-ignored. Back it up somewhere private, or employees will
  need to re-register.
- `/docs` and the OpenAPI schema are disabled by default. Set
  `ENABLE_API_DOCS=true` locally if you want them.
