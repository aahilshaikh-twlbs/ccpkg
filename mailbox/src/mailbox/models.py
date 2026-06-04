from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class Presence:
    session_id: str
    label: str
    cwd: str
    boards: List[str]          # boards[0] = repo board; boards[1:] = named boards
    joined: float
    last_heartbeat: float
    status: str                # "active" | "offline"
    team: Optional[str] = None
    member: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Presence":
        return cls(
            session_id=d["session_id"],
            label=d["label"],
            cwd=d["cwd"],
            boards=list(d.get("boards", [])),
            joined=d["joined"],
            last_heartbeat=d["last_heartbeat"],
            status=d["status"],
            team=d.get("team"),
            member=d.get("member"),
        )


@dataclass
class Claim:
    id: str                    # "clm_" + 12 hex
    board: str
    session_id: str
    label: str
    paths: List[str]           # ABSOLUTE path globs (may contain ** and *)
    kind: str                  # "auto" | "explicit"
    created: float
    expires: float
    released: bool = False
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        return cls(
            id=d["id"],
            board=d["board"],
            session_id=d["session_id"],
            label=d["label"],
            paths=list(d.get("paths", [])),
            kind=d["kind"],
            created=d["created"],
            expires=d["expires"],
            released=d.get("released", False),
            note=d.get("note"),
        )


@dataclass
class Message:
    id: str                    # "msg_" + 12 hex
    board: str
    from_session: str
    from_label: str
    to: str                    # session_id | label | "*"
    kind: str                  # "note"|"release-request"|"dep-signal"|"handoff"|"done"
    body: str
    created: float
    read_by: List[str] = field(default_factory=list)
    ref_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            id=d["id"],
            board=d["board"],
            from_session=d["from_session"],
            from_label=d["from_label"],
            to=d["to"],
            kind=d["kind"],
            body=d["body"],
            created=d["created"],
            read_by=list(d.get("read_by", [])),
            ref_paths=list(d.get("ref_paths", [])),
        )
