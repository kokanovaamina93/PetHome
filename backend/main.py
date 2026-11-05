
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlalchemy import create_engine, ForeignKey, String, Integer, Text, DateTime, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from pwdlib import PasswordHash
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from io import BytesIO
from uuid import uuid4
import secrets

BASE = Path(__file__).resolve().parent
engine = create_engine(f"sqlite:///{BASE / 'pethome.db'}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine)
SECRET = os.environ.get("PETHOME_SECRET_KEY", "")
if not SECRET:
    raise RuntimeError("Set PETHOME_SECRET_KEY before starting the server.")
hasher = PasswordHash.recommended()
app = FastAPI(title="PetHome API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
class Animal(Base):
    __tablename__="animals"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    age: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="available")
    breed: Mapped[str] = mapped_column(String(100), default="")
    sex: Mapped[str] = mapped_column(String(20), default="")
    size: Mapped[str] = mapped_column(String(20), default="")
    temperament: Mapped[str] = mapped_column(String(100), default="")
    activity_level: Mapped[str] = mapped_column(String(30), default="")
    good_with_kids: Mapped[str] = mapped_column(String(20), default="unknown")
    good_with_pets: Mapped[str] = mapped_column(String(20), default="unknown")
    vaccinated: Mapped[str] = mapped_column(String(20), default="unknown")
    sterilized: Mapped[str] = mapped_column(String(20), default="unknown")
    special_needs: Mapped[str] = mapped_column(Text, default="")
    age_group: Mapped[str] = mapped_column(String(20), default="")
class Application(Base):
    __tablename__="applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    animal: Mapped[Animal] = relationship()
class ApplicationHistory(Base):
    __tablename__="application_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    old_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__="audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# Non-destructive migration: preserve existing pethome.db and all applications.
Base.metadata.create_all(engine)
with engine.begin() as conn:
    for table, columns in {
        "users": {"is_active":"INTEGER NOT NULL DEFAULT 1"},
        "animals": {"breed":"VARCHAR(100) NOT NULL DEFAULT ''", "sex":"VARCHAR(20) NOT NULL DEFAULT ''",
          "size":"VARCHAR(20) NOT NULL DEFAULT ''", "temperament":"VARCHAR(100) NOT NULL DEFAULT ''",
          "activity_level":"VARCHAR(30) NOT NULL DEFAULT ''", "good_with_kids":"VARCHAR(20) NOT NULL DEFAULT 'unknown'",
          "good_with_pets":"VARCHAR(20) NOT NULL DEFAULT 'unknown'", "vaccinated":"VARCHAR(20) NOT NULL DEFAULT 'unknown'",
          "sterilized":"VARCHAR(20) NOT NULL DEFAULT 'unknown'", "special_needs":"TEXT NOT NULL DEFAULT ''",
          "age_group":"VARCHAR(20) NOT NULL DEFAULT ''"}
    }.items():
        existing={row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        for col,sql_type in columns.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}"))
UPLOADS=BASE/'uploads'
UPLOADS.mkdir(exist_ok=True)
app.mount('/uploads', StaticFiles(directory=str(UPLOADS)), name='uploads')
def db():
    with SessionLocal() as session: yield session
def user_from_token(authorization: Optional[str]=Header(default=None), session:Session=Depends(db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Необходимо войти")
    try:
        payload=jwt.decode(authorization[7:],SECRET,algorithms=["HS256"])
        uid=int(payload["sub"])
    except (jwt.InvalidTokenError,ValueError,KeyError):
        raise HTTPException(401,"Недействительный токен")
    user=session.get(User,uid)
    if not user or not user.is_active: raise HTTPException(401,"Аккаунт недоступен")
    return user
def admin(user:User=Depends(user_from_token)):
    if user.role not in ("admin","owner"): raise HTTPException(403,"Недостаточно прав")
    return user
def owner(user:User=Depends(user_from_token)):
    if user.role!="owner": raise HTTPException(403,"Только владелец управляет командой")
    return user
def audit(session,actor,action,detail=""):
    session.add(AuditLog(actor_id=actor.id,action=action,detail=detail))
def animal_json(a):
    return {k:getattr(a,k) for k in ("id","name","type","age","city","description","image_url","status","breed","sex","size","temperament","activity_level","good_with_kids","good_with_pets","vaccinated","sterilized","special_needs","age_group")}
def app_json(a):
    return {"id":a.id,"animal_id":a.animal_id,"user_id":a.user_id,"full_name":a.full_name,"phone":a.phone,"comment":a.comment,"status":a.status,"created_at":a.created_at.isoformat(),"animals":{"name":a.animal.name}}

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8,max_length=128)
class ApplicationIn(BaseModel):
    animal_id: int
    full_name: str = Field(min_length=2,max_length=120)
    phone: str = Field(min_length=6,max_length=40)
    comment: str = Field(default="",max_length=2000)
class AnimalIn(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    type: str = Field(min_length=1,max_length=30)
    age: str = Field(min_length=1,max_length=40)
    city: str = Field(min_length=1,max_length=100)
    description: str = Field(max_length=4000)
    image_url: str = Field(max_length=2000)
    status: str="available"
    breed: str = Field(default="",max_length=100)
    sex: str = Field(default="",max_length=20)
    size: str = Field(default="",max_length=20)
    temperament: str = Field(default="",max_length=100)
    activity_level: str = Field(default="",max_length=30)
    good_with_kids: str = "unknown"
    good_with_pets: str = "unknown"
    vaccinated: str = "unknown"
    sterilized: str = "unknown"
    special_needs: str = Field(default="",max_length=2000)
    age_group: str = ""
class StatusIn(BaseModel):
    status: str

@app.post("/auth/register",status_code=201)
def register(data:Credentials, session:Session=Depends(db)):
    email=str(data.email).lower()
    if session.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email уже зарегистрирован")
    u=User(email=email,password_hash=hasher.hash(data.password),role="user")
    session.add(u);session.commit()
    return {"message":"Аккаунт создан"}
@app.post("/auth/login")
def login(data:Credentials,session:Session=Depends(db)):
    u=session.scalar(select(User).where(User.email==str(data.email).lower()))
    if not u or not u.is_active or not hasher.verify(data.password,u.password_hash): raise HTTPException(401,"Неверный email или пароль")
    token=jwt.encode({"sub":str(u.id),"exp":datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm="HS256")
    return {"access_token":token,"token_type":"bearer","user":{"id":u.id,"email":u.email,"role":u.role}}
@app.get("/auth/me")
def me(u:User=Depends(user_from_token)):
    return {"id":u.id,"email":u.email,"role":u.role}
@app.get("/animals")
def animals(session:Session=Depends(db)):
    return [animal_json(a) for a in session.scalars(select(Animal).where(Animal.status=="available").order_by(Animal.id.desc())).all()]
@app.post("/applications",status_code=201)
def apply(data:ApplicationIn,u:User=Depends(user_from_token),session:Session=Depends(db)):
    a=session.get(Animal,data.animal_id)
    if not a or a.status!="available": raise HTTPException(404,"Животное недоступно")
    if session.scalar(select(Application).where(Application.user_id==u.id,Application.animal_id==a.id,Application.status.in_(["new","reviewing","approved"]))):
        raise HTTPException(409,"У вас уже есть активная заявка")
    application=Application(**data.model_dump(),user_id=u.id)
    session.add(application);session.commit();session.refresh(application)
    return app_json(application)
@app.get("/applications/me")
def my_applications(u:User=Depends(user_from_token),session:Session=Depends(db)):
    return [app_json(a) for a in session.scalars(select(Application).where(Application.user_id==u.id).order_by(Application.id.desc())).all()]
@app.get("/admin/applications")
def all_applications(_=Depends(admin),session:Session=Depends(db)):
    return [app_json(a) for a in session.scalars(select(Application).order_by(Application.id.desc())).all()]
@app.patch("/admin/applications/{application_id}")
def change_status(application_id:int,data:StatusIn,u:User=Depends(admin),session:Session=Depends(db)):
    if data.status not in ("new","reviewing","approved","rejected"): raise HTTPException(422,"Неизвестный статус")
    a=session.get(Application,application_id)
    if not a: raise HTTPException(404,"Заявка не найдена")
    old=a.status
    if old!=data.status:
        a.status=data.status
        session.add(ApplicationHistory(application_id=a.id,changed_by=u.id,old_status=old,new_status=data.status))
        audit(session,u,"application.status",f"Заявка #{a.id}: {old} → {data.status}")
        session.commit()
    return app_json(a)
@app.post("/admin/animals",status_code=201)
def add_animal(data:AnimalIn,u:User=Depends(admin),session:Session=Depends(db)):
    if data.status not in ("available","reserved","adopted","archived"): raise HTTPException(422,"Неизвестный статус животного")
    a=Animal(**data.model_dump());session.add(a);session.flush();audit(session,u,"animal.create",f"Животное #{a.id}: {a.name}");session.commit();session.refresh(a)
    return animal_json(a)
@app.put("/admin/animals/{animal_id}")
def edit_animal(animal_id:int,data:AnimalIn,u:User=Depends(admin),session:Session=Depends(db)):
    a=session.get(Animal,animal_id)
    if not a: raise HTTPException(404,"Животное не найдено")
    if data.status not in ("available","reserved","adopted","archived"): raise HTTPException(422,"Неизвестный статус животного")
    for k,v in data.model_dump().items(): setattr(a,k,v)
    audit(session,u,"animal.update",f"Животное #{a.id}: {a.name}, статус {a.status}")
    session.commit()
    return animal_json(a)

@app.get("/admin/animals")
def admin_animals(_=Depends(admin),session:Session=Depends(db)):
    return [animal_json(a) for a in session.scalars(select(Animal).order_by(Animal.id.desc())).all()]

@app.get("/admin/users")
def admin_users(_=Depends(admin),session:Session=Depends(db)):
    return [{"id":u.id,"email":u.email,"role":u.role,"is_active":bool(u.is_active)} for u in session.scalars(select(User).order_by(User.id.desc())).all()]

@app.get("/admin/history")
def admin_history(_=Depends(admin),session:Session=Depends(db)):
    entries=session.scalars(select(ApplicationHistory).order_by(ApplicationHistory.id.desc())).all()
    return [{"id":h.id,"application_id":h.application_id,"changed_by":h.changed_by,"old_status":h.old_status,"new_status":h.new_status,"created_at":h.created_at.isoformat()} for h in entries]

@app.get("/admin/stats")
def admin_stats(_=Depends(admin),session:Session=Depends(db)):
    animals=session.scalars(select(Animal)).all()
    apps=session.scalars(select(Application)).all()
    return {"animals":len(animals),"available":sum(a.status=="available" for a in animals),"adopted":sum(a.status=="adopted" for a in animals),"applications":len(apps),"new":sum(a.status=="new" for a in apps),"reviewing":sum(a.status=="reviewing" for a in apps),"approved":sum(a.status=="approved" for a in apps)}


@app.post("/admin/upload")
async def upload_photo(file:UploadFile=File(...),u:User=Depends(admin),session:Session=Depends(db)):
    # Read only up to limit + 1; reject oversized and deceptive files.
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: raise HTTPException(413,"Максимальный размер файла — 5 МБ")
    try:
        if raw[:5]==b"%PDF-":
            try:
                import fitz
                doc=fitz.open(stream=raw,filetype="pdf")
                if doc.page_count<1: raise ValueError("PDF пуст")
                page=doc.load_page(0)
                pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
                img=Image.open(BytesIO(pix.tobytes("png")))
                doc.close()
            except ImportError:
                raise HTTPException(422,"Для PDF установите PyMuPDF из requirements.txt")
        else:
            img=Image.open(BytesIO(raw))
            if img.format not in ("JPEG","PNG","WEBP"):
                raise ValueError("Неподдерживаемый формат")
        img=ImageOps.exif_transpose(img)
        if img.width*img.height>25_000_000: raise ValueError("Слишком большое разрешение")
        img.thumbnail((1600,1600))
        if img.mode not in ("RGB","L"): img=img.convert("RGB")
        name=secrets.token_hex(16)+'.webp'
        img.save(UPLOADS/name,'WEBP',quality=84)
    except HTTPException: raise
    except Exception:
        raise HTTPException(422,"Нужен корректный JPG, PNG, WEBP или PDF")
    audit(session,u,"photo.upload",name)
    session.commit()
    return {"image_url":f"http://127.0.0.1:8000/uploads/{name}"}

class TeamRoleIn(BaseModel):
    role: str
class TeamActiveIn(BaseModel):
    is_active: bool
class TeamInviteIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12,max_length=128)

@app.get('/owner/team')
def owner_team(_=Depends(owner),session:Session=Depends(db)):
    return [{"id":u.id,"email":u.email,"role":u.role,"is_active":bool(u.is_active)} for u in session.scalars(select(User).order_by(User.id)).all()]

@app.post('/owner/team',status_code=201)
def owner_create_admin(data:TeamInviteIn,actor:User=Depends(owner),session:Session=Depends(db)):
    # Owner-created account with a temporary password; share it privately and change it after login.
    email=str(data.email).lower()
    if session.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email уже используется")
    u=User(email=email,password_hash=hasher.hash(data.password),role="admin")
    session.add(u);session.flush();audit(session,actor,"team.create",f"Сотрудник #{u.id}: {email}")
    session.commit()
    return {"id":u.id,"email":u.email,"role":u.role}

@app.patch('/owner/team/{user_id}/role')
def owner_change_role(user_id:int,data:TeamRoleIn,actor:User=Depends(owner),session:Session=Depends(db)):
    if data.role not in ('admin','user'): raise HTTPException(422,"Можно назначить admin или user")
    target=session.get(User,user_id)
    if not target: raise HTTPException(404,"Пользователь не найден")
    if target.role=='owner' or target.id==actor.id: raise HTTPException(403,"Нельзя изменять владельца")
    previous=target.role;target.role=data.role
    audit(session,actor,"team.role",f"#{target.id}: {previous} → {data.role}");session.commit()
    return {"id":target.id,"role":target.role}

@app.patch('/owner/team/{user_id}/active')
def owner_change_active(user_id:int,data:TeamActiveIn,actor:User=Depends(owner),session:Session=Depends(db)):
    target=session.get(User,user_id)
    if not target: raise HTTPException(404,"Пользователь не найден")
    if target.role=='owner' or target.id==actor.id: raise HTTPException(403,"Нельзя блокировать владельца")
    target.is_active=int(data.is_active)
    audit(session,actor,"team.active",f"#{target.id}: {'active' if data.is_active else 'blocked'}")
    session.commit();return {"id":target.id,"is_active":bool(target.is_active)}

@app.get('/admin/activity')
def activity(_=Depends(admin),session:Session=Depends(db)):
    entries=session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(60)).all()
    ids={a.actor_id for a in entries}
    names={u.id:u.email for u in session.scalars(select(User).where(User.id.in_(ids))).all()} if ids else {}
    return [{"id":a.id,"actor":names.get(a.actor_id,"#"+str(a.actor_id)),"action":a.action,"detail":a.detail,"created_at":a.created_at.isoformat()} for a in entries]

@app.get('/admin/analytics')
def analytics(days:int=30,_=Depends(admin),session:Session=Depends(db)):
    if days not in (7,30,90): raise HTTPException(422,"Период: 7, 30 или 90 дней")
    cutoff=datetime.utcnow()-timedelta(days=days)
    apps=session.scalars(select(Application).where(Application.created_at>=cutoff)).all()
    by_day={}
    for a in apps:
        k=a.created_at.date().isoformat()
        by_day[k]=by_day.get(k,0)+1
    animals=session.scalars(select(Animal)).all()
    return {"period_days":days,"applications_by_day":[{"date":(datetime.utcnow().date()-timedelta(days=i)).isoformat(),"count":by_day.get((datetime.utcnow().date()-timedelta(days=i)).isoformat(),0)} for i in reversed(range(days))],"application_statuses":{k:sum(a.status==k for a in apps) for k in ('new','reviewing','approved','rejected')},"animal_statuses":{k:sum(a.status==k for a in animals) for k in ('available','reserved','adopted','archived')},"adopted":sum(a.status=='adopted' for a in animals)}

class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12,max_length=128)
@app.post('/auth/change-password')
def change_password(data:PasswordChangeIn,u:User=Depends(user_from_token),session:Session=Depends(db)):
    if not hasher.verify(data.current_password,u.password_hash): raise HTTPException(403,"Неверный текущий пароль")
    u.password_hash=hasher.hash(data.new_password)
    session.commit();return {"message":"Пароль изменён"}
