
import os
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4
import json as jsonlib

import recommender

import jwt
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Header,
    UploadFile,
    File,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import (
    create_engine,
    ForeignKey,
    String,
    Integer,
    Text,
    DateTime,
    select,
    text,
    inspect,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
    Session,
)


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE = Path(__file__).resolve().parent

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{BASE / 'pethome.db'}",
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1,
    )

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)

SECRET = os.environ.get("PETHOME_SECRET_KEY", "")

if not SECRET:
    raise RuntimeError(
        "Set PETHOME_SECRET_KEY before starting the server."
    )

hasher = PasswordHash.recommended()


# ============================================================
# 2. FASTAPI AND CORS
# ============================================================

app = FastAPI(
    title="PetHome API",
    version="1.0",
)

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://pet-home-psbiha709-fariza-amina.vercel.app",
]

EXTRA_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "FRONTEND_ORIGINS", ""
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEFAULT_ORIGINS + EXTRA_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "PetHome API"}


# ============================================================
# 3. DATABASE MODELS
# ============================================================

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(20), default="user"
    )
    is_active: Mapped[int] = mapped_column(
        Integer, default=1
    )


class Animal(Base):
    __tablename__ = "animals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    age: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="available"
    )
    breed: Mapped[str] = mapped_column(
        String(100), default=""
    )
    sex: Mapped[str] = mapped_column(
        String(20), default=""
    )
    size: Mapped[str] = mapped_column(
        String(20), default=""
    )
    temperament: Mapped[str] = mapped_column(
        String(100), default=""
    )
    activity_level: Mapped[str] = mapped_column(
        String(30), default=""
    )
    good_with_kids: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )
    good_with_pets: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )
    vaccinated: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )
    sterilized: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )
    special_needs: Mapped[str] = mapped_column(
        Text, default=""
    )
    apartment_ok: Mapped[str] = mapped_column(String(20), default="unknown")
    beginner_ok: Mapped[str] = mapped_column(String(20), default="unknown")
    care_level: Mapped[str] = mapped_column(String(20), default="unknown")
    age_group: Mapped[str] = mapped_column(
        String(20), default=""
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(
        ForeignKey("animals.id")
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(
        Text, default=""
    )
    status: Mapped[str] = mapped_column(
        String(30), default="new"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    # заявка подана из блока ИИ-рекомендаций (для бизнес-метрики конверсии)
    recommendation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    animal: Mapped[Animal] = relationship()


class AppSetting(Base):
    """Настройки, меняемые без перезапуска (переключатель ИИ)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")


class RecommendationLog(Base):
    """Журнал ИИ-подбора: без свободного текста пользователя (только длина и анкета)."""
    __tablename__ = "recommendation_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(20))          # ai | fallback | disabled
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(20), default="")
    recommended_ids: Mapped[str] = mapped_column(Text, default="[]")
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    text_length: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")


class ApplicationHistory(Base):
    __tablename__ = "application_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id")
    )
    changed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )
    old_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(
        Text, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


# ============================================================
# 4. DATABASE INITIALIZATION
# ============================================================

Base.metadata.create_all(engine)

# Compatibility migration for existing SQLite databases
# and PostgreSQL databases created from older schemas.

MISSING_COLUMNS = {
    "users": {
        "is_active": "INTEGER NOT NULL DEFAULT 1",
    },
    "animals": {
        "breed": "VARCHAR(100) NOT NULL DEFAULT ''",
        "sex": "VARCHAR(20) NOT NULL DEFAULT ''",
        "size": "VARCHAR(20) NOT NULL DEFAULT ''",
        "temperament": "VARCHAR(100) NOT NULL DEFAULT ''",
        "activity_level": "VARCHAR(30) NOT NULL DEFAULT ''",
        "good_with_kids": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "good_with_pets": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "vaccinated": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "sterilized": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "special_needs": "TEXT NOT NULL DEFAULT ''",
        "age_group": "VARCHAR(20) NOT NULL DEFAULT ''",
        "apartment_ok": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "beginner_ok": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        "care_level": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
    },
    "applications": {
        "recommendation_id": "INTEGER",
    },
}

with engine.begin() as conn:
    inspector = inspect(conn)

    for table_name, columns in MISSING_COLUMNS.items():
        existing = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }

        for column_name, column_type in columns.items():
            if column_name not in existing:
                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )


# Новая пустая база (например, PostgreSQL на Render) заполняется каталогом из data/animals.json
if os.environ.get("SEED_IF_EMPTY", "1") == "1":
    import seed_animals

    with SessionLocal() as _s:
        seed_animals.seed_if_empty(_s, Animal)


# ============================================================
# 5. FILE UPLOADS
# ============================================================

UPLOADS = Path(
    os.environ.get(
        "UPLOAD_DIR",
        str(BASE / "uploads"),
    )
)

UPLOADS.mkdir(parents=True, exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOADS)),
    name="uploads",
)


# ============================================================
# 6. DATABASE DEPENDENCY AND AUTHORIZATION
# ============================================================

def db():
    with SessionLocal() as session:
        yield session


def user_from_token(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Необходимо войти")

    try:
        payload = jwt.decode(
            authorization[7:],
            SECRET,
            algorithms=["HS256"],
        )
        uid = int(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(401, "Недействительный токен")

    user = session.get(User, uid)

    if not user or not user.is_active:
        raise HTTPException(401, "Аккаунт недоступен")

    return user


def admin(user: User = Depends(user_from_token)):
    if user.role not in ("admin", "owner"):
        raise HTTPException(403, "Недостаточно прав")
    return user


def owner(user: User = Depends(user_from_token)):
    if user.role != "owner":
        raise HTTPException(
            403,
            "Только владелец управляет командой",
        )
    return user


def audit(session, actor, action, detail=""):
    session.add(
        AuditLog(
            actor_id=actor.id,
            action=action,
            detail=detail,
        )
    )


# ============================================================
# 7. JSON HELPERS
# ============================================================

PUBLIC_URL = (
    os.environ.get("PUBLIC_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")


def public_image(url):
    # старые карточки хранят http://127.0.0.1:8000/uploads/... — на Render такой адрес не открывается
    if url and "/uploads/" in url and url.startswith(("http://127.0.0.1", "http://localhost", "/uploads/")):
        return PUBLIC_URL + url[url.index("/uploads/"):]
    return url


def animal_json(a):
    d = {
        k: getattr(a, k)
        for k in (
            "id",
            "name",
            "type",
            "age",
            "city",
            "description",
            "image_url",
            "status",
            "breed",
            "sex",
            "size",
            "temperament",
            "activity_level",
            "good_with_kids",
            "good_with_pets",
            "vaccinated",
            "sterilized",
            "special_needs",
            "age_group",
            "apartment_ok",
            "beginner_ok",
            "care_level",
        )
    }
    d["image_url"] = public_image(d["image_url"])
    return d


def app_json(a):
    return {
        "id": a.id,
        "animal_id": a.animal_id,
        "user_id": a.user_id,
        "full_name": a.full_name,
        "phone": a.phone,
        "comment": a.comment,
        "status": a.status,
        "created_at": a.created_at.isoformat(),
        "animals": {"name": a.animal.name},
    }


# ============================================================
# 8. PYDANTIC SCHEMAS
# ============================================================

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )


class ApplicationIn(BaseModel):
    animal_id: int
    full_name: str = Field(
        min_length=2,
        max_length=120,
    )
    phone: str = Field(
        min_length=6,
        max_length=40,
    )
    comment: str = Field(
        default="",
        max_length=2000,
    )
    recommendation_id: Optional[int] = None


class AnimalIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=30)
    age: str = Field(min_length=1, max_length=40)
    city: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=4000)
    image_url: str = Field(max_length=2000)
    status: str = "available"
    breed: str = Field(default="", max_length=100)
    sex: str = Field(default="", max_length=20)
    size: str = Field(default="", max_length=20)
    temperament: str = Field(default="", max_length=100)
    activity_level: str = Field(default="", max_length=30)
    good_with_kids: str = "unknown"
    good_with_pets: str = "unknown"
    vaccinated: str = "unknown"
    sterilized: str = "unknown"
    special_needs: str = Field(default="", max_length=2000)
    age_group: str = ""
    apartment_ok: str = "unknown"
    beginner_ok: str = "unknown"
    care_level: str = "unknown"


class StatusIn(BaseModel):
    status: str


# ============================================================
# 9. AUTHENTICATION
# ============================================================

@app.post("/auth/register", status_code=201)
def register(
    data: Credentials,
    session: Session = Depends(db),
):
    email = str(data.email).lower()

    if session.scalar(
        select(User).where(User.email == email)
    ):
        raise HTTPException(
            409,
            "Email уже зарегистрирован",
        )

    u = User(
        email=email,
        password_hash=hasher.hash(data.password),
        role="user",
    )

    session.add(u)
    session.commit()

    return {"message": "Аккаунт создан"}


@app.post("/auth/login")
def login(
    data: Credentials,
    session: Session = Depends(db),
):
    u = session.scalar(
        select(User).where(
            User.email == str(data.email).lower()
        )
    )

    if (
        not u
        or not u.is_active
        or not hasher.verify(
            data.password,
            u.password_hash,
        )
    ):
        raise HTTPException(
            401,
            "Неверный email или пароль",
        )

    token = jwt.encode(
        {
            "sub": str(u.id),
            "exp": (
                datetime.now(timezone.utc)
                + timedelta(hours=8)
            ),
        },
        SECRET,
        algorithm="HS256",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": u.id,
            "email": u.email,
            "role": u.role,
        },
    }


@app.get("/auth/me")
def me(u: User = Depends(user_from_token)):
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
    }


# ============================================================
# 10. ANIMALS AND APPLICATIONS
# ============================================================

@app.get("/animals")
def animals(session: Session = Depends(db)):
    return [
        animal_json(a)
        for a in session.scalars(
            select(Animal)
            .where(Animal.status == "available")
            .order_by(Animal.id.desc())
        ).all()
    ]


@app.post("/applications", status_code=201)
def apply(
    data: ApplicationIn,
    u: User = Depends(user_from_token),
    session: Session = Depends(db),
):
    a = session.get(Animal, data.animal_id)

    if not a or a.status != "available":
        raise HTTPException(
            404,
            "Животное недоступно",
        )

    existing = session.scalar(
        select(Application).where(
            Application.user_id == u.id,
            Application.animal_id == a.id,
            Application.status.in_(
                ["new", "reviewing", "approved"]
            ),
        )
    )

    if existing:
        raise HTTPException(
            409,
            "У вас уже есть активная заявка",
        )

    application = Application(
        **data.model_dump(),
        user_id=u.id,
    )

    session.add(application)
    session.commit()
    session.refresh(application)

    return app_json(application)


@app.get("/applications/me")
def my_applications(
    u: User = Depends(user_from_token),
    session: Session = Depends(db),
):
    return [
        app_json(a)
        for a in session.scalars(
            select(Application)
            .where(Application.user_id == u.id)
            .order_by(Application.id.desc())
        ).all()
    ]


# ============================================================
# 11. ADMIN APPLICATIONS
# ============================================================

@app.get("/admin/applications")
def all_applications(
    _=Depends(admin),
    session: Session = Depends(db),
):
    return [
        app_json(a)
        for a in session.scalars(
            select(Application).order_by(
                Application.id.desc()
            )
        ).all()
    ]


@app.patch("/admin/applications/{application_id}")
def change_status(
    application_id: int,
    data: StatusIn,
    u: User = Depends(admin),
    session: Session = Depends(db),
):
    if data.status not in (
        "new",
        "reviewing",
        "approved",
        "rejected",
    ):
        raise HTTPException(
            422,
            "Неизвестный статус",
        )

    a = session.get(Application, application_id)

    if not a:
        raise HTTPException(
            404,
            "Заявка не найдена",
        )

    old = a.status

    if old != data.status:
        a.status = data.status

        session.add(
            ApplicationHistory(
                application_id=a.id,
                changed_by=u.id,
                old_status=old,
                new_status=data.status,
            )
        )

        audit(
            session,
            u,
            "application.status",
            f"Заявка #{a.id}: {old} → {data.status}",
        )

        session.commit()

    return app_json(a)


# ============================================================
# 12. ADMIN ANIMALS
# ============================================================

@app.post("/admin/animals", status_code=201)
def add_animal(
    data: AnimalIn,
    u: User = Depends(admin),
    session: Session = Depends(db),
):
    if data.status not in (
        "available",
        "reserved",
        "adopted",
        "archived",
    ):
        raise HTTPException(
            422,
            "Неизвестный статус животного",
        )

    a = Animal(**data.model_dump())

    session.add(a)
    session.flush()

    audit(
        session,
        u,
        "animal.create",
        f"Животное #{a.id}: {a.name}",
    )

    session.commit()
    session.refresh(a)

    return animal_json(a)


@app.put("/admin/animals/{animal_id}")
def edit_animal(
    animal_id: int,
    data: AnimalIn,
    u: User = Depends(admin),
    session: Session = Depends(db),
):
    a = session.get(Animal, animal_id)

    if not a:
        raise HTTPException(
            404,
            "Животное не найдено",
        )

    if data.status not in (
        "available",
        "reserved",
        "adopted",
        "archived",
    ):
        raise HTTPException(
            422,
            "Неизвестный статус животного",
        )

    for k, v in data.model_dump().items():
        setattr(a, k, v)

    audit(
        session,
        u,
        "animal.update",
        f"Животное #{a.id}: {a.name}, статус {a.status}",
    )

    session.commit()

    return animal_json(a)


@app.get("/admin/animals")
def admin_animals(
    _=Depends(admin),
    session: Session = Depends(db),
):
    return [
        animal_json(a)
        for a in session.scalars(
            select(Animal).order_by(
                Animal.id.desc()
            )
        ).all()
    ]


@app.get("/admin/users")
def admin_users(
    _=Depends(admin),
    session: Session = Depends(db),
):
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_active": bool(u.is_active),
        }
        for u in session.scalars(
            select(User).order_by(User.id.desc())
        ).all()
    ]


@app.get("/admin/history")
def admin_history(
    _=Depends(admin),
    session: Session = Depends(db),
):
    entries = session.scalars(
        select(ApplicationHistory).order_by(
            ApplicationHistory.id.desc()
        )
    ).all()

    return [
        {
            "id": h.id,
            "application_id": h.application_id,
            "changed_by": h.changed_by,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "created_at": h.created_at.isoformat(),
        }
        for h in entries
    ]


@app.get("/admin/stats")
def admin_stats(
    _=Depends(admin),
    session: Session = Depends(db),
):
    all_animals = session.scalars(
        select(Animal)
    ).all()

    apps = session.scalars(
        select(Application)
    ).all()

    return {
        "animals": len(all_animals),
        "available": sum(
            a.status == "available"
            for a in all_animals
        ),
        "adopted": sum(
            a.status == "adopted"
            for a in all_animals
        ),
        "applications": len(apps),
        "new": sum(
            a.status == "new"
            for a in apps
        ),
        "reviewing": sum(
            a.status == "reviewing"
            for a in apps
        ),
        "approved": sum(
            a.status == "approved"
            for a in apps
        ),
    }


# ============================================================
# 13. IMAGE UPLOAD
# ============================================================

@app.post("/admin/upload")
async def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    u: User = Depends(admin),
    session: Session = Depends(db),
):
    raw = await file.read(
        5 * 1024 * 1024 + 1
    )

    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(
            413,
            "Максимальный размер файла — 5 МБ",
        )

    try:
        if raw[:5] == b"%PDF-":
            try:
                import fitz

                doc = fitz.open(
                    stream=raw,
                    filetype="pdf",
                )

                try:
                    if doc.page_count < 1:
                        raise ValueError("PDF пуст")

                    page = doc.load_page(0)

                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(1.5, 1.5),
                        alpha=False,
                    )

                    img = Image.open(
                        BytesIO(
                            pix.tobytes("png")
                        )
                    )
                finally:
                    doc.close()

            except ImportError:
                raise HTTPException(
                    422,
                    "Для PDF установите PyMuPDF из requirements.txt",
                )
        else:
            img = Image.open(BytesIO(raw))

            if img.format not in (
                "JPEG",
                "PNG",
                "WEBP",
            ):
                raise ValueError(
                    "Неподдерживаемый формат"
                )

        img = ImageOps.exif_transpose(img)

        if img.width * img.height > 25_000_000:
            raise ValueError(
                "Слишком большое разрешение"
            )

        img.thumbnail((1600, 1600))

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        name = secrets.token_hex(16) + ".webp"

        img.save(
            UPLOADS / name,
            "WEBP",
            quality=84,
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            422,
            "Нужен корректный JPG, PNG, WEBP или PDF",
        )

    audit(
        session,
        u,
        "photo.upload",
        name,
    )

    session.commit()

    # Use the actual API URL rather than localhost.
    image_url = str(
        request.url_for("uploads", path=name)
    )

    return {"image_url": image_url}


# ============================================================
# 14. TEAM MANAGEMENT SCHEMAS
# ============================================================

class TeamRoleIn(BaseModel):
    role: str


class TeamActiveIn(BaseModel):
    is_active: bool


class TeamInviteIn(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=12,
        max_length=128,
    )


# ============================================================
# 15. OWNER TEAM MANAGEMENT
# ============================================================

@app.get("/owner/team")
def owner_team(
    _=Depends(owner),
    session: Session = Depends(db),
):
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_active": bool(u.is_active),
        }
        for u in session.scalars(
            select(User).order_by(User.id)
        ).all()
    ]


@app.post("/owner/team", status_code=201)
def owner_create_admin(
    data: TeamInviteIn,
    actor: User = Depends(owner),
    session: Session = Depends(db),
):
    email = str(data.email).lower()

    if session.scalar(
        select(User).where(User.email == email)
    ):
        raise HTTPException(
            409,
            "Email уже используется",
        )

    u = User(
        email=email,
        password_hash=hasher.hash(data.password),
        role="admin",
    )

    session.add(u)
    session.flush()

    audit(
        session,
        actor,
        "team.create",
        f"Сотрудник #{u.id}: {email}",
    )

    session.commit()

    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
    }


@app.patch("/owner/team/{user_id}/role")
def owner_change_role(
    user_id: int,
    data: TeamRoleIn,
    actor: User = Depends(owner),
    session: Session = Depends(db),
):
    if data.role not in ("admin", "user"):
        raise HTTPException(
            422,
            "Можно назначить admin или user",
        )

    target = session.get(User, user_id)

    if not target:
        raise HTTPException(
            404,
            "Пользователь не найден",
        )

    if target.role == "owner" or target.id == actor.id:
        raise HTTPException(
            403,
            "Нельзя изменять владельца",
        )

    previous = target.role
    target.role = data.role

    audit(
        session,
        actor,
        "team.role",
        f"#{target.id}: {previous} → {data.role}",
    )

    session.commit()

    return {
        "id": target.id,
        "role": target.role,
    }


@app.patch("/owner/team/{user_id}/active")
def owner_change_active(
    user_id: int,
    data: TeamActiveIn,
    actor: User = Depends(owner),
    session: Session = Depends(db),
):
    target = session.get(User, user_id)

    if not target:
        raise HTTPException(
            404,
            "Пользователь не найден",
        )

    if target.role == "owner" or target.id == actor.id:
        raise HTTPException(
            403,
            "Нельзя блокировать владельца",
        )

    target.is_active = int(data.is_active)

    audit(
        session,
        actor,
        "team.active",
        (
            f"#{target.id}: "
            f"{'active' if data.is_active else 'blocked'}"
        ),
    )

    session.commit()

    return {
        "id": target.id,
        "is_active": bool(target.is_active),
    }


# ============================================================
# 16. ADMIN ACTIVITY
# ============================================================

@app.get("/admin/activity")
def activity(
    _=Depends(admin),
    session: Session = Depends(db),
):
    entries = session.scalars(
        select(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(60)
    ).all()

    ids = {
        a.actor_id
        for a in entries
    }

    names = (
        {
            u.id: u.email
            for u in session.scalars(
                select(User).where(
                    User.id.in_(ids)
                )
            ).all()
        }
        if ids
        else {}
    )

    return [
        {
            "id": a.id,
            "actor": names.get(
                a.actor_id,
                "#" + str(a.actor_id),
            ),
            "action": a.action,
            "detail": a.detail,
            "created_at": a.created_at.isoformat(),
        }
        for a in entries
    ]


# ============================================================
# 17. ADMIN ANALYTICS
# ============================================================

@app.get("/admin/analytics")
def analytics(
    days: int = 30,
    _=Depends(admin),
    session: Session = Depends(db),
):
    if days not in (7, 30, 90):
        raise HTTPException(
            422,
            "Период: 7, 30 или 90 дней",
        )

    cutoff = datetime.utcnow() - timedelta(
        days=days
    )

    apps = session.scalars(
        select(Application).where(
            Application.created_at >= cutoff
        )
    ).all()

    by_day = {}

    for a in apps:
        k = a.created_at.date().isoformat()
        by_day[k] = by_day.get(k, 0) + 1

    all_animals = session.scalars(
        select(Animal)
    ).all()

    return {
        "period_days": days,
        "applications_by_day": [
            {
                "date": (
                    datetime.utcnow().date()
                    - timedelta(days=i)
                ).isoformat(),
                "count": by_day.get(
                    (
                        datetime.utcnow().date()
                        - timedelta(days=i)
                    ).isoformat(),
                    0,
                ),
            }
            for i in reversed(range(days))
        ],
        "application_statuses": {
            k: sum(
                a.status == k
                for a in apps
            )
            for k in (
                "new",
                "reviewing",
                "approved",
                "rejected",
            )
        },
        "animal_statuses": {
            k: sum(
                a.status == k
                for a in all_animals
            )
            for k in (
                "available",
                "reserved",
                "adopted",
                "archived",
            )
        },
        "adopted": sum(
            a.status == "adopted"
            for a in all_animals
        ),
    }


# ============================================================
# 18. PASSWORD CHANGE
# ============================================================

class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(
        min_length=12,
        max_length=128,
    )


@app.post("/auth/change-password")
def change_password(
    data: PasswordChangeIn,
    u: User = Depends(user_from_token),
    session: Session = Depends(db),
):
    if not hasher.verify(
        data.current_password,
        u.password_hash,
    ):
        raise HTTPException(
            403,
            "Неверный текущий пароль",
        )

    u.password_hash = hasher.hash(
        data.new_password
    )

    session.commit()

    return {
        "message": "Пароль изменён"
    }


# ============================================================
# ИИ-ПОДБОР ПИТОМЦА (ЛЗ 12)
# ============================================================

AI_NOTICE = (
    "Рекомендации сформированы с помощью искусственного интеллекта. "
    "Совместимость и условия содержания необходимо подтвердить с сотрудником приюта."
)
FALLBACK_NOTICE = (
    "Облачная модель сейчас недоступна — показан подбор по правилам без ИИ. "
    "Совместимость необходимо подтвердить с сотрудником приюта."
)
DISABLED_NOTICE = (
    "ИИ-подбор временно отключён — показан подбор по правилам. "
    "Совместимость необходимо подтвердить с сотрудником приюта."
)


def ai_enabled(session: Session) -> bool:
    row = session.get(AppSetting, "ai_enabled")
    if row is not None:
        return row.value == "1"
    return os.environ.get("AI_ENABLED", "1") != "0"


def optional_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(db),
):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
        return session.get(User, int(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError, KeyError):
        return None


class RecommendIn(BaseModel):
    profile: dict = Field(default_factory=dict)
    message: str = Field(default="", max_length=1000)


class AiToggleIn(BaseModel):
    enabled: bool


@app.get("/ai/status")
def ai_status(session: Session = Depends(db)):
    return {
        "enabled": ai_enabled(session),
        "provider_configured": bool(recommender.AI_API_KEY) or "localhost" in recommender.AI_BASE_URL,
        "model": recommender.AI_MODEL,
        "prompt_version": recommender.PROMPT_VERSION,
        "notice": AI_NOTICE,
    }


@app.post("/ai/recommend")
def ai_recommend(
    data: RecommendIn,
    u: Optional[User] = Depends(optional_user),
    session: Session = Depends(db),
):
    animals = [
        animal_json(a)
        for a in session.scalars(select(Animal).where(Animal.status == "available")).all()
    ]
    result = recommender.recommend_for_site(
        data.profile, data.message, animals, ai_enabled(session)
    )
    by_id = {a["id"]: a for a in animals}
    reasons = {p["animal_id"]: p.get("reason", "") for p in result.get("pairs", [])}
    usage = result.get("usage") or {}
    log = RecommendationLog(
        user_id=u.id if u else None,
        mode=result.get("mode", ""),
        model=result.get("model", "keyword-rules") or "",
        prompt_version=recommender.PROMPT_VERSION if result.get("mode") == "ai" else "rules-v1",
        action=result.get("action", ""),
        recommended_ids=jsonlib.dumps(result.get("top", [])),
        profile_json=jsonlib.dumps(recommender.clean_profile(data.profile), ensure_ascii=False),
        text_length=len(data.message or ""),
        latency_ms=int(float(result.get("latency_s", 0)) * 1000),
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        error=result.get("error", ""),
    )
    session.add(log)
    session.commit()
    mode = result.get("mode")
    return {
        "recommendation_id": log.id,
        "mode": mode,
        "notice": AI_NOTICE if mode == "ai" else DISABLED_NOTICE if mode == "disabled" else FALLBACK_NOTICE,
        "action": result.get("action"),
        "question": result.get("question"),
        "handoff": result.get("action") != "recommend",
        "items": [
            {**by_id[i], "reason": reasons.get(i, "")} for i in result.get("top", []) if i in by_id
        ],
        "alternatives": [
            {**by_id[i], "reason": reasons.get(i, "")}
            for i in result.get("alternatives", []) if i in by_id
        ],
    }


class HandoffRequest(Base):
    """Вопрос, переданный сотруднику, когда ИИ не смог безопасно подобрать животное."""
    __tablename__ = "ai_handoff"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recommendation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")


Base.metadata.create_all(engine, tables=[HandoffRequest.__table__])


class HandoffIn(BaseModel):
    recommendation_id: Optional[int] = None
    message: str = Field(default="", max_length=1000)


@app.post("/ai/handoff", status_code=201)
def ai_handoff(data: HandoffIn, u: User = Depends(user_from_token), session: Session = Depends(db)):
    h = HandoffRequest(user_id=u.id, recommendation_id=data.recommendation_id,
                       message=recommender.scrub_pii(data.message))
    session.add(h)
    session.commit()
    return {"id": h.id, "message": "Вопрос передан сотруднику приюта"}


@app.get("/admin/ai/handoffs")
def admin_handoffs(_=Depends(admin), session: Session = Depends(db)):
    rows = session.scalars(select(HandoffRequest).order_by(HandoffRequest.id.desc()).limit(100)).all()
    emails = {u.id: u.email for u in session.scalars(select(User)).all()}
    return [{"id": h.id, "created_at": h.created_at.isoformat(), "email": emails.get(h.user_id, ""),
             "message": h.message, "recommendation_id": h.recommendation_id, "status": h.status} for h in rows]


@app.patch("/admin/ai")
def admin_ai_toggle(data: AiToggleIn, u: User = Depends(admin), session: Session = Depends(db)):
    row = session.get(AppSetting, "ai_enabled") or AppSetting(key="ai_enabled")
    row.value = "1" if data.enabled else "0"
    session.add(row)
    audit(session, u, "ai.toggle", "включён" if data.enabled else "отключён")
    session.commit()
    return {"enabled": data.enabled}


@app.get("/admin/ai/stats")
def admin_ai_stats(_=Depends(admin), session: Session = Depends(db)):
    logs = session.scalars(select(RecommendationLog)).all()
    with_recs = [x for x in logs if x.recommended_ids not in ("[]", "")]
    apps_from_reco = session.scalars(
        select(Application).where(Application.recommendation_id.is_not(None))
    ).all()
    n = len(logs) or 1
    return {
        "enabled": ai_enabled(session),
        "requests": len(logs),
        "ai_share": round(sum(x.mode == "ai" for x in logs) / n, 3),
        "fallback_share": round(sum(x.mode == "fallback" for x in logs) / n, 3),
        "refusal_share": round(sum(x.action in ("clarify", "no_safe_match") for x in logs) / n, 3),
        "avg_latency_ms": round(sum(x.latency_ms for x in logs) / n),
        "avg_prompt_tokens": round(sum(x.prompt_tokens for x in logs) / n),
        "avg_completion_tokens": round(sum(x.completion_tokens for x in logs) / n),
        "applications_from_recommendations": len(apps_from_reco),
        "conversion": round(len(apps_from_reco) / len(with_recs), 3) if with_recs else None,
    }
