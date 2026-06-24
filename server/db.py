import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast

from passlib.context import CryptContext
from sqlalchemy import Column, delete, desc, func, or_
from sqlalchemy.types import JSON
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Use a pure-Python scheme for test reliability (avoids bcrypt backend quirks in CI/dev containers).
# If you want bcrypt/argon2 in production, add those schemes and verify backend availability.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

DATABASE_URL = os.environ.get("TAVERNTAILS_DATABASE_URL", "sqlite:///./taverntails.db")
engine = create_engine(DATABASE_URL, echo=False)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str | None = Field(default=None, index=True)
    username: str | None = Field(default=None, index=True)
    password_hash: str
    verified: bool = Field(default=False)
    verification_token: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Character(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    name: str
    level: int = Field(default=1)
    class_name: str | None = None
    sheet: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Campaign(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    name: str
    description: str | None = None
    created_at: str | None = None
    archived: bool = Field(default=False)
    gm_user_id: int | None = Field(default=None, foreign_key="user.id")
    gm_mode: str = Field(default="ai")
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Roll(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: str | None = Field(default=None, foreign_key="campaign.id")
    expression: str
    rolls: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    mod: int = Field(default=0)
    total: int = Field(default=0)
    by: str | None = None
    created_at: str | None = None


class CampaignEntity(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    name: str
    entity_type: str = Field(default="npc")
    status: str = Field(default="active")
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: str | None = None


class CampaignHook(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    title: str
    description: str | None = None
    hook_type: str = Field(default="open")
    priority: int = Field(default=0)
    deadline: str | None = None
    status: str = Field(default="active")


class CampaignRelationship(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    source_entity_id: str
    target_entity_id: str
    relation_type: str | None = None
    description: str | None = None


class CampaignChangeLog(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    entity_id: str | None = None
    summary: str | None = None
    caused_by_player_action: bool = Field(default=False)
    created_at: str | None = None


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def create_campaign(owner_id: int, name: str, description: str | None = None) -> Campaign:
    import uuid
    cid = uuid.uuid4().hex[:8]
    camp = Campaign(id=cid, owner_id=owner_id, name=name.strip(), description=description or '', created_at=datetime.now(timezone.utc).isoformat())
    with Session(engine) as session:
        session.add(camp)
        session.commit()
        session.refresh(camp)
    return camp


def get_campaign_by_id(campaign_id: str) -> Campaign | None:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        return session.exec(stmt).first()


def get_character_by_id(character_id: int) -> Character | None:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id)
        return session.exec(stmt).first()


def list_campaigns_for_owner(owner_id: int) -> List[Campaign]:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.owner_id == owner_id)
        return list(session.exec(stmt).all())


def list_campaigns_as_gm(user_id: int) -> List[Campaign]:
    """Return campaigns where user_id is the assigned GM (but is NOT the owner)."""
    with Session(engine) as session:
        stmt = select(Campaign).where(
            Campaign.gm_user_id == user_id,
            Campaign.owner_id != user_id,
        )
        return list(session.exec(stmt).all())


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(default=None, index=True)
    campaign_id: str | None = Field(default=None, index=True)
    sender_id: int | None = Field(default=None, foreign_key="user.id")
    sender_name: str | None = None
    role: str = Field(default="player")
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class PinnedMessage(SQLModel, table=True):
    """Records that a chat message has been pinned in a session."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    message_id: int = Field(foreign_key="chatmessage.id")
    pinned_by_id: int | None = Field(default=None, foreign_key="user.id")
    pinned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FriendRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    from_user_id: int = Field(foreign_key="user.id")
    to_user_id: int = Field(foreign_key="user.id")
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupportTicket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    subject: str
    body: str
    status: str = Field(default="open")  # open | in_progress | resolved | closed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class UserBlock(SQLModel, table=True):
    """Records that `blocker_id` has blocked `blocked_id`."""

    id: int | None = Field(default=None, primary_key=True)
    blocker_id: int = Field(foreign_key="user.id", index=True)
    blocked_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserReport(SQLModel, table=True):
    """A user report filed against another user."""

    id: int | None = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id", index=True)
    reported_id: int = Field(foreign_key="user.id", index=True)
    reason: str  # harassment | spam | hate_speech | cheating | other
    details: str = Field(default="")
    status: str = Field(default="open")  # open | reviewed | dismissed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None


class DirectMessage(SQLModel, table=True):
    """A private message sent from one user to another (outside of sessions)."""

    id: int | None = Field(default=None, primary_key=True)
    sender_id: int = Field(foreign_key="user.id", index=True)
    recipient_id: int = Field(foreign_key="user.id", index=True)
    body: str
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BannedEmail(SQLModel, table=True):
    """A banned or suspended email / email pattern."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    reason: str = Field(default="")
    ban_type: str = Field(default="ban")
    suspended_until: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_id: int | None = Field(default=None, foreign_key="user.id")


# ---------------------------------------------------------------------------
# Campaign Memory System
# ---------------------------------------------------------------------------

class CampaignEntity(SQLModel, table=True):
    """A named entity in the campaign world (NPC, location, faction, backstory, story_thread, world_event)."""

    id: str = Field(primary_key=True)
    campaign_id: str = Field(index=True, foreign_key="campaign.id")
    entity_type: str = Field(index=True)  # npc | location | faction | backstory | story_thread | world_event
    name: str = Field(index=True)
    status: str = Field(default="active")  # active | resolved | archived
    visibility: str = Field(default="gm_only")  # gm_only | shared
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CampaignRelationship(SQLModel, table=True):
    """A directional link between two CampaignEntity records."""

    id: str = Field(primary_key=True)
    campaign_id: str = Field(index=True, foreign_key="campaign.id")
    source_entity_id: str = Field(index=True)
    target_entity_id: str = Field(index=True)
    relationship_type: str = Field(default="")
    description: str = Field(default="")
    scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    secrecy_level: str = Field(default="public")  # public | private | hidden
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CampaignHook(SQLModel, table=True):
    """An unresolved story hook, ticking clock, or consequence attached to the campaign."""

    id: str = Field(primary_key=True)
    campaign_id: str = Field(index=True, foreign_key="campaign.id")
    entity_id: str | None = Field(default=None, index=True)
    title: str
    description: str = Field(default="")
    hook_type: str = Field(default="unresolved")  # unresolved | ticking_clock | escalation | consequence
    priority: int = Field(default=5)  # 1 (low) – 10 (critical)
    status: str = Field(default="active")  # active | triggered | resolved
    deadline: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CampaignChangeLog(SQLModel, table=True):
    """Immutable record of a significant change to a campaign entity."""

    id: str = Field(primary_key=True)
    campaign_id: str = Field(index=True, foreign_key="campaign.id")
    entity_id: str = Field(index=True)
    session_id: str | None = Field(default=None)
    change_type: str = Field(default="update")  # create | update | resolve | reveal | damage | death
    summary: str
    before_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    after_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    caused_by_player_action: bool = Field(default=False)
    related_event_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _profile_with_identity(user: User) -> dict[str, Any]:
    data = dict(user.profile or {})
    if user.email:
        data.setdefault("email", user.email)
    if user.username:
        data.setdefault("username", user.username)
    if "name" not in data and user.username:
        data["name"] = user.username
    return data


def update_campaign(campaign_id: str, owner_id: int, updates: dict[str, Any]) -> Campaign | None:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        if 'name' in updates and updates['name']:
            camp.name = updates['name']
        if 'description' in updates:
            camp.description = updates['description']
        if 'archived' in updates:
            camp.archived = bool(updates['archived'])
        session.add(camp)
        session.commit()
        session.refresh(camp)
        return camp


def get_campaign_settings(campaign_id: str, owner_id: int) -> Dict[str, Any] | None:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        meta = dict(camp.metadata_json or {})
        settings = meta.get("settings")
        return dict(settings) if isinstance(settings, dict) else {}


def set_campaign_settings(campaign_id: str, owner_id: int, settings: Dict[str, Any]) -> Campaign | None:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        meta = dict(camp.metadata_json or {})
        meta["settings"] = dict(settings)
        camp.metadata_json = meta
        session.add(camp)
        session.commit()
        session.refresh(camp)
        return camp


def get_campaign_variables(campaign_id: str, owner_id: int) -> Dict[str, Any] | None:
    """Return the campaign variables dict, or {} if not yet set, or None if not found/forbidden."""
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        meta = dict(camp.metadata_json or {})
        variables = meta.get("variables")
        return dict(variables) if isinstance(variables, dict) else {}


def set_campaign_variables(campaign_id: str, owner_id: int, variables: Dict[str, Any]) -> Campaign | None:
    """Persist campaign variables into metadata_json['variables']."""
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        meta = dict(camp.metadata_json or {})
        meta["variables"] = dict(variables)
        camp.metadata_json = meta
        session.add(camp)
        session.commit()
        session.refresh(camp)
        return camp


def delete_campaign(campaign_id: str, owner_id: int) -> bool:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return False
        session.delete(camp)
        session.commit()
        return True


def purge_campaigns(owner_id: int, name_tokens: List[str] | None = None) -> int:
    tokens = [t.strip().lower() for t in (name_tokens or []) if t and t.strip()]
    with Session(engine) as session:
        stmt = delete(Campaign).where(Campaign.owner_id == owner_id)
        if tokens:
            stmt = stmt.where(or_(*[func.lower(Campaign.name).like(f"%{token}%") for token in tokens]))
        result = session.exec(stmt)
        session.commit()
        try:
            return int(result.rowcount or 0)
        except Exception:
            return 0


def add_session_to_campaign(campaign_id: str, owner_id: int, session_id: str) -> Campaign | None:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return None
        meta = dict(camp.metadata_json or {})
        sessions = list(meta.get('sessions', []) or [])
        if session_id not in sessions:
            sessions.append(session_id)
        meta['sessions'] = sessions
        camp.metadata_json = meta
        session.add(camp)
        session.commit()
        session.refresh(camp)
        return camp


def create_roll(campaign_id: str | None, expression: str, rolls: list[int], mod: int, total: int, by: str | None) -> Roll:
    rec = Roll(campaign_id=campaign_id, expression=expression, rolls=rolls, mod=mod, total=total, by=by, created_at=datetime.now(timezone.utc).isoformat())
    with Session(engine) as session:
        session.add(rec)
        session.commit()
        session.refresh(rec)
    return rec


def list_rolls_for_campaign(campaign_id: str) -> list[Roll]:
    with Session(engine) as session:
        stmt = select(Roll).where(Roll.campaign_id == campaign_id)
        return list(session.exec(stmt).all())


def log_chat_message(
    message: str,
    *,
    session_id: str | None = None,
    campaign_id: str | None = None,
    sender_id: int | None = None,
    sender_name: str | None = None,
    role: str = "player",
    metadata: dict[str, Any] | None = None,
) -> ChatMessage:
    record = ChatMessage(
        session_id=session_id,
        campaign_id=campaign_id,
        sender_id=sender_id,
        sender_name=sender_name,
        role=role,
        message=message,
        metadata_json=metadata or {},
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def list_chat_messages(
    *, session_id: str | None = None, campaign_id: str | None = None, limit: int = 100
) -> list[ChatMessage]:
    with Session(engine) as session:
        stmt = select(ChatMessage)
        if session_id:
            stmt = stmt.where(ChatMessage.session_id == session_id)
        if campaign_id:
            stmt = stmt.where(ChatMessage.campaign_id == campaign_id)
        stmt = stmt.order_by(desc(cast(Any, ChatMessage.created_at))).limit(limit)
        return list(reversed(list(session.exec(stmt).all())))


def delete_chat_message(message_id: int, sender_id: int) -> bool:
    """Delete a chat message. Only the original sender may delete their own messages."""
    with Session(engine) as session:
        msg = session.exec(select(ChatMessage).where(ChatMessage.id == message_id)).first()
        if not msg:
            return False
        if msg.sender_id != sender_id:
            return False
        session.delete(msg)
        # Clean up any pin record for this message
        pin = session.exec(select(PinnedMessage).where(PinnedMessage.message_id == message_id)).first()
        if pin:
            session.delete(pin)
        session.commit()
        return True


def pin_message(session_id: str, message_id: int, pinned_by_id: int | None = None) -> PinnedMessage | None:
    """Pin a message in a session. Idempotent — returns the existing record if already pinned."""
    with Session(engine) as session:
        msg = session.exec(
            select(ChatMessage).where(ChatMessage.id == message_id, ChatMessage.session_id == session_id)
        ).first()
        if not msg:
            return None
        existing = session.exec(
            select(PinnedMessage).where(PinnedMessage.session_id == session_id, PinnedMessage.message_id == message_id)
        ).first()
        if existing:
            return existing
        pin = PinnedMessage(session_id=session_id, message_id=message_id, pinned_by_id=pinned_by_id)
        session.add(pin)
        session.commit()
        session.refresh(pin)
        return pin


def unpin_message(session_id: str, message_id: int) -> bool:
    """Remove a pin from a message. Returns True if a pin was removed."""
    with Session(engine) as session:
        pin = session.exec(
            select(PinnedMessage).where(PinnedMessage.session_id == session_id, PinnedMessage.message_id == message_id)
        ).first()
        if not pin:
            return False
        session.delete(pin)
        session.commit()
        return True


def list_pinned_messages(session_id: str) -> list[ChatMessage]:
    """Return ChatMessage records that are pinned in session_id, ordered oldest-pin first."""
    with Session(engine) as session:
        pins = list(
            session.exec(
                select(PinnedMessage)
                .where(PinnedMessage.session_id == session_id)
                .order_by(cast(Any, PinnedMessage.pinned_at))
            ).all()
        )
        if not pins:
            return []
        ids = [p.message_id for p in pins]
        # SQLModel's Column type doesn't expose .in_() to mypy, but it is valid at runtime.
        msgs = list(session.exec(select(ChatMessage).where(ChatMessage.id.in_(ids))).all())  # type: ignore[attr-defined]
        msg_map = {m.id: m for m in msgs}
        return [msg_map[i] for i in ids if i in msg_map]


def send_friend_request(from_identifier: str, to_identifier: str) -> FriendRequest:
    from_user = get_user_by_identifier(from_identifier)
    to_user = get_user_by_identifier(to_identifier)
    if not from_user or not to_user:
        raise ValueError("User not found")
    if from_user.id == to_user.id:
        raise ValueError("Cannot friend yourself")
    with Session(engine) as session:
        # prevent duplicate pending or accepted
        stmt = select(FriendRequest).where(
            FriendRequest.from_user_id == from_user.id,
            FriendRequest.to_user_id == to_user.id,
        )
        existing = session.exec(stmt).first()
        if existing and existing.status in ("pending", "accepted"):
            raise ValueError("Request already exists")
        req = FriendRequest(from_user_id=from_user.id, to_user_id=to_user.id, status="pending")
        session.add(req)
        session.commit()
        session.refresh(req)
        return req


def list_friends_and_requests(identifier: str):
    user = get_user_by_identifier(identifier)
    if not user:
        return {"friends": [], "pending": []}
    user_id = user.id
    if user_id is None:
        return {"friends": [], "pending": []}
    with Session(engine) as session:
        # accepted friendships where user is either from or to
        stmt_fr = select(FriendRequest).where(
            ((FriendRequest.from_user_id == user_id) | (FriendRequest.to_user_id == user_id)),
            FriendRequest.status == "accepted",
        )
        accepted = list(session.exec(stmt_fr).all())
        friend_ids: set[int] = set()
        for fr in accepted:
            friend_ids.add(fr.to_user_id if fr.from_user_id == user_id else fr.from_user_id)
        friends = []
        if friend_ids:
            stmt_users = select(User).where(cast(Any, User.id).in_(list(friend_ids)))
            friends = [_profile_with_identity(u) for u in session.exec(stmt_users).all()]

        # incoming pending requests
        stmt_pending = select(FriendRequest).where(FriendRequest.to_user_id == user_id, FriendRequest.status == "pending")
        pending = []
        pending_rows = session.exec(stmt_pending).all()
        if pending_rows:
            from_ids = [r.from_user_id for r in pending_rows]
            user_map = {
                u.id: _profile_with_identity(u)
                for u in session.exec(select(User).where(cast(Any, User.id).in_(from_ids))).all()
                if u.id is not None
            }
            for r in pending_rows:
                pending.append({"from_id": r.from_user_id, "from_profile": user_map.get(r.from_user_id, {})})
        return {"friends": friends, "pending": pending}


def accept_friend_request(to_identifier: str, from_identifier: str) -> bool:
    to_user = get_user_by_identifier(to_identifier)
    from_user = get_user_by_identifier(from_identifier)
    if not to_user or not from_user:
        return False
    with Session(engine) as session:
        stmt = select(FriendRequest).where(
            FriendRequest.from_user_id == from_user.id,
            FriendRequest.to_user_id == to_user.id,
        )
        req = session.exec(stmt).first()
        if not req or req.status != "pending":
            return False
        req.status = "accepted"
        session.add(req)
        session.commit()
        session.refresh(req)
        return True


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed.lower() if trimmed else None


def _normalize_username(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def get_user_by_identifier(identifier: str) -> User | None:
    if not identifier:
        return None
    identifier = identifier.strip()
    if not identifier:
        return None
    with Session(engine) as session:
        lowered = identifier.lower()
        # check email (case-insensitive)
        stmt = select(User).where(func.lower(User.email) == lowered)
        res = session.exec(stmt).first()
        if res:
            return res
        # check username (case-insensitive)
        stmt = select(User).where(func.lower(User.username) == lowered)
        return session.exec(stmt).first()


def search_users(query: str, *, limit: int = 10) -> List[User]:
    q = (query or "").strip()
    if not q:
        return []
    q_lower = q.lower()
    like = f"%{q_lower}%"
    with Session(engine) as session:
        stmt = (
            select(User)
            .where(
                (func.lower(User.username).like(like))
                | (func.lower(User.email).like(like))
            )
            .order_by(User.username)
            .limit(max(1, min(int(limit or 10), 25)))
        )
        return list(session.exec(stmt).all())


def create_user(email: str, password: str, username: str | None = None, profile: Dict[str, Any] | None = None) -> User:
    clean_email = _normalize_email(email)
    if not clean_email:
        raise ValueError("Email required")
    clean_username = _normalize_username(username)
    hashed = hash_password(password)
    token = __import__('uuid').uuid4().hex
    user = User(email=clean_email, username=clean_username, password_hash=hashed, verified=False, verification_token=token, profile=profile or {})
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def ensure_dev_user():
    """Create a default dev user if missing so local logins always work."""
    email = _normalize_email(os.environ.get('TAVERNTAILS_DEV_EMAIL', 'test@example.com')) or 'test@example.com'
    password = os.environ.get('TAVERNTAILS_DEV_PASSWORD', 'secret')
    username = _normalize_username(os.environ.get('TAVERNTAILS_DEV_USERNAME', 'tester'))
    with Session(engine) as session:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        existing = session.exec(stmt).first()
        if existing:
            updated = False
            if existing.username != username:
                existing.username = username
                updated = True
            if not existing.verified:
                existing.verified = True
                updated = True
            if existing.verification_token:
                existing.verification_token = None
                updated = True
            # Always keep the dev password in sync so we know the credentials
            if not verify_password(password, existing.password_hash):
                existing.password_hash = hash_password(password)
                updated = True
            desired_name = username or email.split('@')[0]
            prefs = existing.profile or {}
            if prefs.get('name') != desired_name:
                prefs['name'] = desired_name
                existing.profile = prefs
                updated = True
            if updated:
                session.add(existing)
                session.commit()
                session.refresh(existing)
            return existing
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            verified=True,
            verification_token=None,
            profile={'name': username or email.split('@')[0]},
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def is_admin_user(user: User) -> bool:
    if not user:
        return False
    profile = user.profile or {}
    if profile.get("admin") is True:
        return True
    roles = profile.get("roles")
    if isinstance(roles, list) and any(str(r).lower() == "admin" for r in roles):
        return True
    email = (user.email or "").lower()
    if email:
        allow = [e.strip().lower() for e in (os.environ.get("TAVERNTAILS_ADMIN_EMAILS") or "").split(",") if e.strip()]
        if email in allow:
            return True
    return False


def set_admin_mode(user_id: int, enabled: bool) -> User | None:
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        dbu = session.exec(stmt).first()
        if not dbu:
            return None
        profile = dict(dbu.profile or {})
        prefs = profile.setdefault("preferences", {})
        if isinstance(prefs, dict):
            prefs["admin_mode"] = bool(enabled)
        profile["preferences"] = prefs
        dbu.profile = profile
        session.add(dbu)
        session.commit()
        session.refresh(dbu)
        return dbu


def ensure_seed_users():
    """Ensure admin + test users exist (for local development)."""
    admin_email = _normalize_email(os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")) or "admin@example.com"
    admin_password = os.environ.get("TAVERNTAILS_ADMIN_PASSWORD", "secret")
    admin_username = _normalize_username(os.environ.get("TAVERNTAILS_ADMIN_USERNAME", "Admin"))
    test_email = _normalize_email(os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")) or "bilbo@example.com"
    test_password = os.environ.get("TAVERNTAILS_TEST_PASSWORD", "secret")
    test_username = _normalize_username(os.environ.get("TAVERNTAILS_TEST_USERNAME", "BilboBaggins"))

    def _ensure(email: str, password: str, username: str | None, profile: Dict[str, Any]) -> User:
        with Session(engine) as session:
            stmt = select(User).where(func.lower(User.email) == email.lower())
            existing = session.exec(stmt).first()
            if existing:
                updated = False
                if username and existing.username != username:
                    existing.username = username
                    updated = True
                if not existing.verified:
                    existing.verified = True
                    updated = True
                if existing.verification_token:
                    existing.verification_token = None
                    updated = True
                if not verify_password(password, existing.password_hash):
                    existing.password_hash = hash_password(password)
                    updated = True
                merged = dict(existing.profile or {})
                merged.update(profile or {})
                if merged != (existing.profile or {}):
                    existing.profile = merged
                    updated = True
                if updated:
                    session.add(existing)
                    session.commit()
                    session.refresh(existing)
                return existing
            user = User(
                email=email,
                username=username,
                password_hash=hash_password(password),
                verified=True,
                verification_token=None,
                profile=profile,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    _ensure(
        admin_email,
        admin_password,
        admin_username,
        {
            "name": admin_username or admin_email.split("@")[0],
            "email": admin_email,
            "admin": True,
            "preferences": {"admin_mode": True},
        },
    )

    _ensure(
        test_email,
        test_password,
        test_username,
        {
            "name": "Bilbo Baggins",
            "email": test_email,
            "preferences": {"admin_mode": False},
        },
    )


def set_verification_token(email: str, token: str):
    with Session(engine) as session:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        user = session.exec(stmt).first()
        if not user:
            return None
        user.verification_token = token
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def verify_user(email: str, token: str) -> bool:
    with Session(engine) as session:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        user = session.exec(stmt).first()
        if not user:
            return False
        if user.verification_token != token:
            return False
        user.verified = True
        user.verification_token = None
        session.add(user)
        session.commit()
        return True


def authenticate_user(identifier: str, password: str) -> User | None:
    user = get_user_by_identifier(identifier)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def update_profile(email_or_name: str, profile_updates: dict[str, Any]) -> User | None:
    user = get_user_by_identifier(email_or_name)
    if not user:
        return None
    with Session(engine) as session:
        stmt = select(User).where(User.id == user.id)
        dbu = session.exec(stmt).first()
        if not dbu:
            return None
        dbu.profile.update(profile_updates)
        session.add(dbu)
        session.commit()
        session.refresh(dbu)
        return dbu


def list_characters_for_user(owner_id: int) -> list[Character]:
    with Session(engine) as session:
        stmt = select(Character).where(Character.owner_id == owner_id)
        return list(session.exec(stmt).all())


def create_character(owner_id: int, name: str, level: int = 1, class_name: str | None = None, sheet: dict[str, Any] | None = None) -> Character:
    payload = Character(owner_id=owner_id, name=name.strip(), level=max(1, level), class_name=class_name.strip() if class_name else None, sheet=sheet or {})
    with Session(engine) as session:
        session.add(payload)
        session.commit()
        session.refresh(payload)
        return payload


def get_character_for_owner(character_id: int, owner_id: int) -> Character | None:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
        return session.exec(stmt).first()


def _apply_sheet_patch(sheet: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(sheet)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = {**result[k], **v}
        else:
            result[k] = v
    return result


def update_character(character_id: int, owner_id: int, updates: Dict[str, Any]) -> Character | None:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
        char = session.exec(stmt).first()
        if not char:
            return None
        if 'name' in updates and updates['name']:
            char.name = updates['name'].strip()
        if 'class_name' in updates:
            value = updates['class_name']
            char.class_name = value.strip() if value else None
        if 'level' in updates and updates['level']:
            char.level = max(1, int(updates['level']))
        if 'sheet' in updates and isinstance(updates['sheet'], dict):
            char.sheet = updates['sheet']
        if 'sheet_patch' in updates and isinstance(updates['sheet_patch'], dict):
            existing = dict(char.sheet) if isinstance(char.sheet, dict) else {}
            char.sheet = _apply_sheet_patch(existing, updates['sheet_patch'])
        session.add(char)
        session.commit()
        session.refresh(char)
        return char


def delete_character(character_id: int, owner_id: int) -> bool:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
        char = session.exec(stmt).first()
        if not char:
            return False
        session.delete(char)
        session.commit()
        return True


def delete_character_any(character_id: int) -> bool:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id)
        char = session.exec(stmt).first()
        if not char:
            return False
        session.delete(char)
        session.commit()
        return True


def update_character_any(character_id: int, updates: Dict[str, Any]) -> Character | None:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id)
        char = session.exec(stmt).first()
        if not char:
            return None
        if 'name' in updates and updates['name']:
            char.name = updates['name'].strip()
        if 'class_name' in updates:
            value = updates['class_name']
            char.class_name = value.strip() if value else None
        if 'level' in updates and updates['level']:
            char.level = max(1, int(updates['level']))
        if 'sheet' in updates and isinstance(updates['sheet'], dict):
            char.sheet = updates['sheet']
        session.add(char)
        session.commit()
        session.refresh(char)
        return char


def purge_characters(owner_id: int, name_tokens: List[str] | None = None) -> int:
    tokens = [t.strip().lower() for t in (name_tokens or []) if t and t.strip()]
    with Session(engine) as session:
        stmt = delete(Character).where(Character.owner_id == owner_id)
        if tokens:
            stmt = stmt.where(or_(*[func.lower(Character.name).like(f"%{token}%") for token in tokens]))
        result = session.exec(stmt)
        session.commit()
        try:
            return int(result.rowcount or 0)
        except Exception:
            return 0


def get_beyond20_domains_for(identifier: str) -> List[str]:
    user = get_user_by_identifier(identifier)
    if not user:
        return []
    prefs = user.profile.get('preferences', {})
    return prefs.get('beyond20', {}).get('domains', [])


def set_beyond20_domains_for(identifier: str, domains: list[str]) -> list[str] | None:
    user = get_user_by_identifier(identifier)
    if not user:
        return None
    with Session(engine) as session:
        stmt = select(User).where(User.id == user.id)
        dbu = session.exec(stmt).first()
        if not dbu:
            return None
        # Copy the profile to ensure SQLAlchemy/JSON type detects the change
        new_profile = dict(dbu.profile or {})
        prefs = new_profile.setdefault('preferences', {})
        prefs.setdefault('beyond20', {})['domains'] = domains
        dbu.profile = new_profile
        session.add(dbu)
        session.commit()
        session.refresh(dbu)
        return domains


def get_beyond20_relay_token_for_user_id(user_id: int) -> str | None:
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return None
        prefs = (user.profile or {}).get("preferences", {})
        return (prefs.get("beyond20", {}) or {}).get("relay_token")


def _set_beyond20_relay_token_for_user_id(user_id: int, token: str) -> str | None:
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return None
        new_profile = dict(user.profile or {})
        prefs = new_profile.setdefault("preferences", {})
        beyond20 = prefs.setdefault("beyond20", {})
        beyond20["relay_token"] = token
        user.profile = new_profile
        session.add(user)
        session.commit()
        session.refresh(user)
        return token


def ensure_beyond20_relay_token_for_user_id(user_id: int) -> str | None:
    existing = get_beyond20_relay_token_for_user_id(user_id)
    if existing:
        return existing
    token = secrets.token_hex(24)
    return _set_beyond20_relay_token_for_user_id(user_id, token)


def rotate_beyond20_relay_token_for_user_id(user_id: int) -> str | None:
    token = secrets.token_hex(24)
    return _set_beyond20_relay_token_for_user_id(user_id, token)


def get_user_by_beyond20_relay_token(token: str) -> User | None:
    if not token:
        return None
    token = token.strip()
    if not token:
        return None
    with Session(engine) as session:
        stmt = select(User)
        users = session.exec(stmt).all()
        for user in users:
            prefs = (user.profile or {}).get("preferences", {})
            relay = (prefs.get("beyond20", {}) or {}).get("relay_token")
            if relay == token:
                return user
        return None


# ---------------------------------------------------------------------------
# Steward Dashboard SSO integration
# ---------------------------------------------------------------------------

def _unique_username(session, base: str) -> str:
    """Return base username, appending a counter if already taken."""
    candidate = base.strip() or "Player"
    stmt = select(User).where(func.lower(User.username) == candidate.lower())
    if not session.exec(stmt).first():
        return candidate
    for i in range(2, 100):
        suffixed = f"{candidate}{i}"
        stmt2 = select(User).where(func.lower(User.username) == suffixed.lower())
        if not session.exec(stmt2).first():
            return suffixed
    return candidate + secrets.token_hex(4)


def get_or_create_steward_user(profile_id: str, display_name: str) -> User:
    """Find or create a TavernTails user linked to a Steward Dashboard profile."""
    email = f"{profile_id}@steward.local"
    with Session(engine) as session:
        user = session.exec(select(User).where(func.lower(User.email) == email.lower())).first()
        if user:
            return user
        user = User(
            email=email,
            username=_unique_username(session, display_name),
            password_hash=hash_password(secrets.token_hex(32)),
            verified=True,
            profile={
                "name": display_name,
                "email": email,
                "steward_profile_id": profile_id,
                "source": "steward_sso",
            },
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def admin_list_users(limit: int = 100, offset: int = 0) -> List[User]:
    """Return all users sorted alphabetically by username (admin use only)."""
    with Session(engine) as session:
        stmt = select(User).order_by(User.username, User.email).offset(offset).limit(max(1, min(int(limit), 200)))
        return list(session.exec(stmt).all())


def admin_count_users() -> int:
    """Return the total number of registered users (admin use only)."""
    with Session(engine) as session:
        return session.exec(select(func.count()).select_from(User)).one()


def admin_get_user(user_id: int) -> User | None:
    """Return a single user by ID (admin use only)."""
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        return session.exec(stmt).first()


def admin_reset_password(user_id: int, new_password: str) -> bool:
    """Reset a user's password (admin use only)."""
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return False
        user.password_hash = hash_password(new_password)
        session.add(user)
        session.commit()
        return True


def update_user_self(user_id: int, *, name: str | None = None, email: str | None = None, username: str | None = None) -> User | None:
    """Update the calling user's own display name, email, and/or username."""
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return None
        if email is not None:
            clean_email = email.strip().lower()
            # uniqueness check — compare lowercased on both sides
            conflict = session.exec(select(User).where(func.lower(User.email) == clean_email, User.id != user_id)).first()
            if conflict:
                raise ValueError("Email already in use by another account.")
            user.email = clean_email
        if username is not None:
            clean_username = _normalize_username(username)
            if clean_username:
                # uniqueness check — normalise the candidate before comparing
                conflict = session.exec(
                    select(User).where(func.lower(User.username) == clean_username.lower(), User.id != user_id)
                ).first()
                if conflict:
                    raise ValueError("Username already taken.")
            user.username = clean_username
        if name is not None:
            new_profile = dict(user.profile or {})
            new_profile["name"] = name.strip()
            user.profile = new_profile
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def change_user_password(user_id: int, current_password: str, new_password: str) -> bool:
    """Verify current_password then set new_password for user_id.  Returns False if current_password is wrong."""
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return False
        if not verify_password(current_password, user.password_hash or ""):
            return False
        user.password_hash = hash_password(new_password)
        session.add(user)
        session.commit()
        return True


def admin_send_notification(user_id: int, title: str, body: str | None = None) -> bool:
    """Append a notification to a user's profile (admin use only)."""
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        user = session.exec(stmt).first()
        if not user:
            return False
        new_profile = dict(user.profile or {})
        notifications: List[Dict[str, Any]] = list(new_profile.get("notifications", []) or [])
        import uuid as _uuid
        notifications.append({
            "id": _uuid.uuid4().hex,
            "title": title,
            "body": body or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
        })
        new_profile["notifications"] = notifications
        user.profile = new_profile
        session.add(user)
        session.commit()
        return True


def admin_list_all_campaigns(limit: int = 100, offset: int = 0) -> List[Campaign]:
    """Return all campaigns across all owners (admin use only)."""
    with Session(engine) as session:
        stmt = select(Campaign).order_by(desc(Campaign.created_at)).offset(offset).limit(max(1, min(int(limit), 200)))
        return list(session.exec(stmt).all())


def admin_search_campaigns(query: str, limit: int = 10) -> List[Campaign]:
    """Search campaigns by name or description using DB-level filtering (admin use only)."""
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q.lower()}%"
    with Session(engine) as session:
        stmt = (
            select(Campaign)
            .where(
                (func.lower(Campaign.name).like(like))
                | (func.lower(Campaign.description).like(like))
            )
            .order_by(desc(Campaign.created_at))
            .limit(max(1, min(int(limit), 25)))
        )
        return list(session.exec(stmt).all())


def admin_archive_campaign(campaign_id: str) -> bool:
    """Archive a campaign by ID regardless of owner (admin use only)."""
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        camp = session.exec(stmt).first()
        if not camp:
            return False
        camp.archived = True
        session.add(camp)
        session.commit()
        return True


def admin_delete_campaign(campaign_id: str) -> bool:
    """Permanently delete a campaign and its dependent rows (admin use only)."""
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        camp = session.exec(stmt).first()
        if not camp:
            return False
        # Bulk-remove dependent rows before deleting the campaign
        session.exec(delete(ChatMessage).where(ChatMessage.campaign_id == campaign_id))
        session.exec(delete(Roll).where(Roll.campaign_id == campaign_id))
        session.delete(camp)
        session.commit()
        return True


def admin_site_stats() -> Dict[str, Any]:
    """Return aggregate site statistics (admin use only)."""
    with Session(engine) as session:
        total_users = session.exec(select(func.count()).select_from(User)).one()
        verified_users = session.exec(select(func.count()).select_from(User).where(User.verified == True)).one()  # noqa: E712
        total_campaigns = session.exec(select(func.count()).select_from(Campaign)).one()
        active_campaigns = session.exec(select(func.count()).select_from(Campaign).where(Campaign.archived == False)).one()  # noqa: E712
        total_characters = session.exec(select(func.count()).select_from(Character)).one()
        total_messages = session.exec(select(func.count()).select_from(ChatMessage)).one()
        return {
            "total_users": int(total_users),
            "verified_users": int(verified_users),
            "total_campaigns": int(total_campaigns),
            "active_campaigns": int(active_campaigns),
            "total_characters": int(total_characters),
            "total_messages": int(total_messages),
        }


# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------

_VALID_TICKET_STATUSES = {"open", "in_progress", "resolved", "closed"}


def create_support_ticket(user_id: int, subject: str, body: str) -> SupportTicket:
    """Create a new support ticket submitted by the given user."""
    ticket = SupportTicket(user_id=user_id, subject=subject.strip(), body=body.strip())
    with Session(engine) as session:
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
    return ticket


def list_support_tickets(status: str | None = None, limit: int = 100, offset: int = 0) -> List[SupportTicket]:
    """List all support tickets, optionally filtered by status (admin use)."""
    with Session(engine) as session:
        stmt = select(SupportTicket)
        if status:
            stmt = stmt.where(SupportTicket.status == status)
        stmt = stmt.order_by(desc(SupportTicket.created_at)).offset(offset).limit(limit)
        return list(session.exec(stmt).all())


def get_support_ticket(ticket_id: int) -> SupportTicket | None:
    """Fetch a single support ticket by ID."""
    with Session(engine) as session:
        return session.exec(select(SupportTicket).where(SupportTicket.id == ticket_id)).first()


def update_ticket_status(ticket_id: int, status: str) -> SupportTicket | None:
    """Update the status of a support ticket (admin use)."""
    if status not in _VALID_TICKET_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {_VALID_TICKET_STATUSES}")
    with Session(engine) as session:
        ticket = session.exec(select(SupportTicket).where(SupportTicket.id == ticket_id)).first()
        if not ticket:
            return None
        ticket.status = status
        ticket.updated_at = datetime.now(timezone.utc)
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
    return ticket


def list_user_support_tickets(user_id: int) -> List[SupportTicket]:
    """Return all tickets submitted by a specific user."""
    with Session(engine) as session:
        stmt = select(SupportTicket).where(SupportTicket.user_id == user_id).order_by(desc(SupportTicket.created_at))
        return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# User blocking
# ---------------------------------------------------------------------------

_VALID_REPORT_REASONS = {"harassment", "spam", "hate_speech", "cheating", "other"}
_VALID_REPORT_STATUSES = {"open", "reviewed", "dismissed"}


def block_user(blocker_id: int, blocked_id: int) -> UserBlock:
    """Block a user. Idempotent — returns existing block if already present."""
    with Session(engine) as session:
        existing = session.exec(
            select(UserBlock).where(UserBlock.blocker_id == blocker_id, UserBlock.blocked_id == blocked_id)
        ).first()
        if existing:
            return existing
        block = UserBlock(blocker_id=blocker_id, blocked_id=blocked_id)
        session.add(block)
        session.commit()
        session.refresh(block)
    return block


def unblock_user(blocker_id: int, blocked_id: int) -> bool:
    """Remove a block. Returns True if a block was removed, False if none existed."""
    with Session(engine) as session:
        existing = session.exec(
            select(UserBlock).where(UserBlock.blocker_id == blocker_id, UserBlock.blocked_id == blocked_id)
        ).first()
        if not existing:
            return False
        session.delete(existing)
        session.commit()
    return True


def is_blocked(blocker_id: int, blocked_id: int) -> bool:
    """Return True if blocker_id has blocked blocked_id."""
    with Session(engine) as session:
        row = session.exec(
            select(UserBlock).where(UserBlock.blocker_id == blocker_id, UserBlock.blocked_id == blocked_id)
        ).first()
    return row is not None


def list_blocks(blocker_id: int) -> List[UserBlock]:
    """Return all blocks created by the given user."""
    with Session(engine) as session:
        return list(
            session.exec(select(UserBlock).where(UserBlock.blocker_id == blocker_id).order_by(desc(UserBlock.created_at))).all()
        )


# ---------------------------------------------------------------------------
# User reporting
# ---------------------------------------------------------------------------


def create_user_report(reporter_id: int, reported_id: int, reason: str, details: str = "") -> UserReport:
    """File a report against reported_id. One report per (reporter, reported, reason) triple."""
    with Session(engine) as session:
        existing = session.exec(
            select(UserReport).where(
                UserReport.reporter_id == reporter_id,
                UserReport.reported_id == reported_id,
                UserReport.reason == reason,
                UserReport.status == "open",
            )
        ).first()
        if existing:
            return existing
        report = UserReport(reporter_id=reporter_id, reported_id=reported_id, reason=reason, details=details.strip())
        session.add(report)
        session.commit()
        session.refresh(report)
    return report


def list_user_reports(status: str | None = None, limit: int = 100, offset: int = 0) -> List[UserReport]:
    """List all user reports (admin use), optionally filtered by status."""
    with Session(engine) as session:
        stmt = select(UserReport)
        if status:
            stmt = stmt.where(UserReport.status == status)
        stmt = stmt.order_by(desc(UserReport.created_at)).offset(offset).limit(limit)
        return list(session.exec(stmt).all())


def get_user_report(report_id: int) -> UserReport | None:
    """Fetch a single user report by ID."""
    with Session(engine) as session:
        return session.exec(select(UserReport).where(UserReport.id == report_id)).first()


def update_report_status(report_id: int, status: str) -> UserReport | None:
    """Update the status of a user report (admin use)."""
    if status not in _VALID_REPORT_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {_VALID_REPORT_STATUSES}")
    with Session(engine) as session:
        report = session.exec(select(UserReport).where(UserReport.id == report_id)).first()
        if not report:
            return None
        report.status = status
        report.reviewed_at = datetime.now(timezone.utc)
        session.add(report)
        session.commit()
        session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Direct messages
# ---------------------------------------------------------------------------


def send_direct_message(sender_id: int, recipient_id: int, body: str) -> DirectMessage:
    """Send a private message from sender to recipient and create a notification for the recipient."""
    msg = DirectMessage(sender_id=sender_id, recipient_id=recipient_id, body=body.strip())
    with Session(engine) as session:
        session.add(msg)
        session.commit()
        session.refresh(msg)

    # Notify recipient
    sender = admin_get_user(sender_id)
    sender_name = (sender.profile or {}).get("name") or (sender.username if sender else None) or "Someone"
    admin_send_notification(
        recipient_id,
        title=f"📨 New message from {sender_name}",
        body=body[:200] if body else "",
    )
    return msg


def get_inbox(user_id: int, limit: int = 50, offset: int = 0) -> List[DirectMessage]:
    """Return messages received by user_id, newest first."""
    with Session(engine) as session:
        stmt = (
            select(DirectMessage)
            .where(DirectMessage.recipient_id == user_id)
            .order_by(desc(DirectMessage.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(stmt).all())


def get_sent_messages(user_id: int, limit: int = 50, offset: int = 0) -> List[DirectMessage]:
    """Return messages sent by user_id, newest first."""
    with Session(engine) as session:
        stmt = (
            select(DirectMessage)
            .where(DirectMessage.sender_id == user_id)
            .order_by(desc(DirectMessage.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(session.exec(stmt).all())


def mark_message_read(message_id: int, recipient_id: int) -> bool:
    """Mark a message as read.  Returns False if not found / not the recipient."""
    with Session(engine) as session:
        msg = session.exec(
            select(DirectMessage).where(DirectMessage.id == message_id, DirectMessage.recipient_id == recipient_id)
        ).first()
        if not msg:
            return False
        msg.read = True
        session.add(msg)
        session.commit()
    return True


def count_unread_messages(user_id: int) -> int:
    """Return the number of unread messages in the user's inbox."""
    with Session(engine) as session:
        return int(session.exec(select(func.count()).select_from(DirectMessage).where(
            DirectMessage.recipient_id == user_id, DirectMessage.read.is_(False)
        )).one())


def delete_direct_message(message_id: int, user_id: int) -> bool:
    """Delete a DM if the caller is the sender or recipient."""
    with Session(engine) as session:
        msg = session.exec(select(DirectMessage).where(DirectMessage.id == message_id)).first()
        if not msg:
            return False
        if msg.sender_id != user_id and msg.recipient_id != user_id:
            return False
        session.delete(msg)
        session.commit()
    return True


# ---------------------------------------------------------------------------
# Email bans / suspensions
# ---------------------------------------------------------------------------


def _email_is_banned_or_suspended(email: str) -> "BannedEmail | None":
    """Return the first active ban/suspension record that matches the email, or None."""
    email_lower = email.lower().strip()
    domain = "@" + email_lower.split("@")[-1] if "@" in email_lower else None
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        rows = session.exec(select(BannedEmail)).all()
        for row in rows:
            pattern = (row.email or "").lower().strip()
            if pattern == email_lower or (domain and pattern == domain):
                if row.ban_type == "ban":
                    return row
                if row.ban_type == "suspend":
                    su = row.suspended_until
                    # Normalize to timezone-aware for comparison
                    if su is not None and su.tzinfo is None:
                        su = su.replace(tzinfo=timezone.utc)
                    if su is None or su > now:
                        return row
    return None


def ban_email(email: str, reason: str = "", ban_type: str = "ban", suspended_until: "datetime | None" = None, created_by_id: int | None = None) -> BannedEmail:
    """Create or update a ban/suspension record."""
    email_lower = email.lower().strip()
    with Session(engine) as session:
        existing = session.exec(select(BannedEmail).where(BannedEmail.email == email_lower)).first()
        if existing:
            existing.reason = reason
            existing.ban_type = ban_type
            existing.suspended_until = suspended_until
            if created_by_id:
                existing.created_by_id = created_by_id
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        record = BannedEmail(
            email=email_lower,
            reason=reason,
            ban_type=ban_type,
            suspended_until=suspended_until,
            created_by_id=created_by_id,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def unban_email(email: str) -> bool:
    """Remove a ban/suspension record for the given email."""
    email_lower = email.lower().strip()
    with Session(engine) as session:
        existing = session.exec(select(BannedEmail).where(BannedEmail.email == email_lower)).first()
        if not existing:
            return False
        session.delete(existing)
        session.commit()
    return True


def list_banned_emails(limit: int = 100, offset: int = 0) -> "List[BannedEmail]":
    """List all ban/suspension records."""
    with Session(engine) as session:
        return list(session.exec(select(BannedEmail).order_by(desc(BannedEmail.created_at)).offset(offset).limit(limit)).all())


# ---------------------------------------------------------------------------
# Admin: reports and tickets per user
# ---------------------------------------------------------------------------


def list_reports_about_user(reported_id: int, limit: int = 100) -> List[UserReport]:
    """Return all reports filed against a specific user (admin use)."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(UserReport).where(UserReport.reported_id == reported_id).order_by(desc(UserReport.created_at)).limit(limit)
            ).all()
        )


def list_tickets_by_user(user_id: int, limit: int = 100) -> List[SupportTicket]:
    """Return all support tickets submitted by a specific user (admin use)."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(SupportTicket).where(SupportTicket.user_id == user_id).order_by(desc(SupportTicket.created_at)).limit(limit)
            ).all()
        )


# ---------------------------------------------------------------------------
# Admin impersonation
# ---------------------------------------------------------------------------


def admin_get_impersonation_token(admin_user: "User", target_user_id: int) -> "str | None":
    """Return a short-lived JWT for impersonating target_user_id (admin only).

    Import here to avoid circular import; auth module depends on db.
    """
    from .auth import create_access_token

    target = admin_get_user(target_user_id)
    if not target:
        return None
    subject = target.email or target.username or str(target.id)
    # 15-minute window so accidental tabs don't stay open long.
    token = create_access_token(subject, expires_delta=timedelta(minutes=15))
    return token


# ---------------------------------------------------------------------------
# Document sharing with friends
# ---------------------------------------------------------------------------


def are_friends(user_id_a: int, user_id_b: int) -> bool:
    """Return True if the two users are confirmed friends."""
    with Session(engine) as session:
        row = session.exec(
            select(FriendRequest).where(
                FriendRequest.status == "accepted",
            ).where(
                or_(
                    (FriendRequest.from_user_id == user_id_a) & (FriendRequest.to_user_id == user_id_b),
                    (FriendRequest.from_user_id == user_id_b) & (FriendRequest.to_user_id == user_id_a),
                )
            )
        ).first()
    return row is not None
