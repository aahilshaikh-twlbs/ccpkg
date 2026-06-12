---
description: Toggle nuke mode — persistent ultracode (xhigh effort + dynamic workflows). `/nuke` to arm, `/nuke off` to disarm.
---

<<NUKE:$ARGUMENTS>>

Nuke mode is a persistent toggle:

- `/nuke` (alias `/nuke arm`) — turns **ultracode** on (xhigh effort + dynamic
  workflows) by writing it to your settings. It applies from your **next**
  session; for the current session run `/effort ultracode` to apply it now.
- `/nuke off` (alias `/nuke disarm`) — turns ultracode back off.

While armed, every session also prefers **persistent agent teams** (TeamCreate +
mboard) over ephemeral subagents for implementation work.

Acknowledge in one line whether nuke mode was just armed or disarmed (based on
the directive injected this turn), then continue with whatever the user asked
for, or await their next instruction.
