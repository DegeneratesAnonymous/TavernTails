import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from passlib.context import CryptContext
from sqlalchemy import Column, desc, func
from sqlalchemy.types import JSON
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Use a pure-Python scheme for test reliability (avoids native bcrypt issues in test venvs)
# In production you may prefer bcrypt/argon2 and install the corresponding packages.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

DATABASE_URL = "sqlite:///./taverntails.db"
engine = create_engine(DATABASE_URL, echo=False)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: Optional[str] = Field(default=None, index=True)
    username: Optional[str] = Field(default=None, index=True)
    password_hash: str
    verified: bool = Field(default=False)
    verification_token: Optional[str] = None
    profile: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Character(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    name: str
    level: int = Field(default=1)
    class_name: Optional[str] = None
    sheet: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Campaign(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    name: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    archived: bool = Field(default=False)
    metadata_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Roll(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: Optional[str] = Field(default=None, foreign_key="campaign.id")
    expression: str
    rolls: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    mod: int = Field(default=0)
    total: int = Field(default=0)
    by: Optional[str] = None
    created_at: Optional[str] = None


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def create_campaign(owner_id: int, name: str, description: Optional[str] = None) -> Campaign:
    import uuid
    cid = uuid.uuid4().hex[:8]
    camp = Campaign(id=cid, owner_id=owner_id, name=name.strip(), description=description or '', created_at=datetime.now(timezone.utc).isoformat())
    with Session(engine) as session:
        session.add(camp)
        session.commit()
        session.refresh(camp)
    return camp


def get_campaign_by_id(campaign_id: str) -> Optional[Campaign]:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        return session.exec(stmt).first()


def list_campaigns_for_owner(owner_id: int) -> List[Campaign]:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.owner_id == owner_id)
        return list(session.exec(stmt).all())


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[str] = Field(default=None, index=True)
    campaign_id: Optional[str] = Field(default=None, index=True)
    sender_id: Optional[int] = Field(default=None, foreign_key="user.id")
    sender_name: Optional[str] = None
    role: str = Field(default="player")
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class FriendRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    from_user_id: int = Field(foreign_key="user.id")
    to_user_id: int = Field(foreign_key="user.id")
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _profile_with_identity(user: User) -> Dict[str, Any]:
    data = dict(user.profile or {})
    if user.email:
        data.setdefault("email", user.email)
    if user.username:
        data.setdefault("username", user.username)
    if "name" not in data and user.username:
        data["name"] = user.username
    return data


def update_campaign(campaign_id: str, owner_id: int, updates: Dict[str, Any]) -> Optional[Campaign]:
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


def delete_campaign(campaign_id: str, owner_id: int) -> bool:
    with Session(engine) as session:
        stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.owner_id == owner_id)
        camp = session.exec(stmt).first()
        if not camp:
            return False
        session.delete(camp)
        session.commit()
        return True


def add_session_to_campaign(campaign_id: str, owner_id: int, session_id: str) -> Optional[Campaign]:
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


def create_roll(campaign_id: Optional[str], expression: str, rolls: List[int], mod: int, total: int, by: Optional[str]) -> Roll:
    rec = Roll(campaign_id=campaign_id, expression=expression, rolls=rolls, mod=mod, total=total, by=by, created_at=datetime.now(timezone.utc).isoformat())
    with Session(engine) as session:
        session.add(rec)
        session.commit()
        session.refresh(rec)
    return rec


def list_rolls_for_campaign(campaign_id: str) -> List[Roll]:
    with Session(engine) as session:
        stmt = select(Roll).where(Roll.campaign_id == campaign_id)
        return list(session.exec(stmt).all())


def log_chat_message(
    message: str,
    *,
    session_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    sender_id: Optional[int] = None,
    sender_name: Optional[str] = None,
    role: str = "player",
    metadata: Optional[Dict[str, Any]] = None,
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
    *, session_id: Optional[str] = None, campaign_id: Optional[str] = None, limit: int = 100
) -> List[ChatMessage]:
    with Session(engine) as session:
        stmt = select(ChatMessage)
        if session_id:
            stmt = stmt.where(ChatMessage.session_id == session_id)
        if campaign_id:
            stmt = stmt.where(ChatMessage.campaign_id == campaign_id)
        stmt = stmt.order_by(desc(cast(Any, ChatMessage.created_at))).limit(limit)
        return list(reversed(list(session.exec(stmt).all())))

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


def _normalize_email(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed.lower() if trimmed else None


def _normalize_username(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def get_user_by_identifier(identifier: str) -> Optional[User]:
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


def create_user(email: str, password: str, username: Optional[str] = None, profile: Optional[Dict[str, Any]] = None) -> User:
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


def authenticate_user(identifier: str, password: str) -> Optional[User]:
    user = get_user_by_identifier(identifier)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def update_profile(email_or_name: str, profile_updates: Dict[str, Any]) -> Optional[User]:
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


def list_characters_for_user(owner_id: int) -> List[Character]:
    with Session(engine) as session:
        stmt = select(Character).where(Character.owner_id == owner_id)
        return list(session.exec(stmt).all())


def create_character(owner_id: int, name: str, level: int = 1, class_name: Optional[str] = None, sheet: Optional[Dict[str, Any]] = None) -> Character:
    payload = Character(owner_id=owner_id, name=name.strip(), level=max(1, level), class_name=class_name.strip() if class_name else None, sheet=sheet or {})
    with Session(engine) as session:
        session.add(payload)
        session.commit()
        session.refresh(payload)
        return payload


def get_character_for_owner(character_id: int, owner_id: int) -> Optional[Character]:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
        return session.exec(stmt).first()


def get_character_by_id(character_id: int) -> Optional[Character]:
    with Session(engine) as session:
        stmt = select(Character).where(Character.id == character_id)
        return session.exec(stmt).first()


def update_character(character_id: int, owner_id: int, updates: Dict[str, Any]) -> Optional[Character]:
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


def get_beyond20_domains_for(identifier: str) -> List[str]:
    user = get_user_by_identifier(identifier)
    if not user:
        return []
    prefs = user.profile.get('preferences', {})
    return prefs.get('beyond20', {}).get('domains', [])


def set_beyond20_domains_for(identifier: str, domains: List[str]) -> Optional[List[str]]:
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
