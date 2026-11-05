import sys
from sqlalchemy import select
from main import SessionLocal, User
if len(sys.argv)!=2: raise SystemExit("Использование: python make_owner.py email@example.com")
with SessionLocal() as s:
    email=sys.argv[1].strip().lower()
    user=s.scalar(select(User).where(User.email==email))
    if not user: raise SystemExit("Сначала зарегистрируйте аккаунт на сайте")
    existing=s.scalar(select(User).where(User.role=='owner'))
    if existing and existing.id!=user.id: raise SystemExit("Owner уже назначен; второго владельца этот скрипт не создаёт")
    user.role='owner';user.is_active=1;s.commit()
    print("Owner назначен:",email)
