import sys
from sqlalchemy import select
from main import SessionLocal, User
if len(sys.argv)!=2: raise SystemExit('Использование: python make_admin.py email@example.com')
with SessionLocal() as s:
    user=s.scalar(select(User).where(User.email==sys.argv[1].lower()))
    if not user: raise SystemExit('Сначала зарегистрируйте этот email на сайте')
    user.role='admin';s.commit()
    print('Роль admin назначена:',user.email)
