# BIRST 2026 — competition workspace

Working directory for the [BIRST 2026](../../docs/06-birst-2026.md) entry.
Team: **Tars Crew 9075** · Level 3 (international) · registered 29 Jul 2026.

## The one rule of this folder

[`TEAM_NAME.txt`](TEAM_NAME.txt) holds the registered team name and is the
**only** authoritative copy of that string. It is 14 bytes, with no trailing
newline and no surrounding whitespace:

```
Tars Crew 9075
```

The submitted `.ork` filename must match it **exactly** or the project is
disqualified. So:

- **Never type the name.** Copy it from that file, every time.
- Verify before submitting: `basename` of the `.ork`, minus `.ork`, must be
  byte-identical to the file's contents.

```sh
# Should print nothing. Anything else means the filename is wrong.
diff <(printf '%s' "$(basename 'Tars Crew 9075.ork' .ork)") TEAM_NAME.txt
```

## Open question before submission

The registration form says the `.ork` filename must match the team name exactly.
Regulations §4.4.1 says to name the file with "the corresponding level **and** the
official team name." Those are different strings. **Confirm with the organizers in
writing and record the answer here** before the file is submitted.

## Validate against a released OpenRocket, not a patched build

This project carries [two unmerged OpenRocket fixes](../../docs/05-open-source.md).
The `.ork` submitted here contains a design, not that code — the evaluation panel
re-simulates it on their own machine, with their own build.

A design validated only against the patched branch can therefore behave
differently, or abort, when the judges open it. **Produce every number that goes
into the submission with a public release of OpenRocket.** Use the patched build
only to understand behaviour, never to generate a result.
