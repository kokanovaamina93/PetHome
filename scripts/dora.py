import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import requests

REPO = os.getenv('GH_REPO', 'kokanoavaamina93/PetHome')
TOKEN = os.getenv('GH_TOKEN')
API = f'https://api.github.com/repos/{REPO}'


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def get_pages(path, key):
    items = []
    page = 1
    while True:
        response = requests.get(
            f'{API}/{path}',
            headers={'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'},
            params={'per_page': 100, 'page': page}, timeout=20,
        )
        response.raise_for_status()
        batch = response.json()
        if key:
            batch = batch[key]
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def main():
    if not TOKEN:
        raise SystemExit('Сначала задайте GH_TOKEN в переменной окружения.')
    deployments = get_pages('deployments', None)
    successful = []
    for deployment in deployments:
        statuses = get_pages(f"deployments/{deployment['id']}/statuses", None)
        successes = [s for s in statuses if s.get('state') == 'success']
        if successes:
            successful.append((deployment, min(successes, key=lambda s: s['created_at'])))
    successful.sort(key=lambda pair: pair[1]['created_at'])
    print('Репозиторий:', REPO)
    print('Успешных развёртываний (в доступной истории):', len(successful))
    if not successful:
        print('Нет данных о развёртываниях. Успешный CI не равен развёртыванию.')
        return
    dates = [dt(s['created_at']) for _, s in successful]
    weeks = max(1, (datetime.now(timezone.utc) - min(dates)).days / 7)
    print(f'Частота развёртываний: {len(successful) / weeks:.2f} в неделю (за период с первого доступного развёртывания)')
    lead_hours = []
    for dep, status in successful:
        sha = dep.get('sha')
        if not sha:
            continue
        r = requests.get(f'{API}/commits/{sha}', headers={'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'}, timeout=20)
        r.raise_for_status()
        committed = dt(r.json()['commit']['committer']['date'])
        hours = (dt(status['created_at']) - committed).total_seconds() / 3600
        if hours >= 0:
            lead_hours.append(hours)
    print(f'Время от коммита до стенда (медиана): {median(lead_hours):.2f} ч' if lead_hours else 'Lead Time: нет данных')
    incident_path = Path(__file__).with_name('incidents.csv')
    with incident_path.open(encoding='utf-8-sig', newline='') as f:
        incidents = [row for row in csv.DictReader(f) if row.get('deployment_id') and row.get('started_at') and row.get('restored_at')]
    valid_ids = {str(d['id']) for d, _ in successful}
    failed_ids = set()
    recovery_minutes = []
    for row in incidents:
        if row['deployment_id'] not in valid_ids:
            continue
        started, restored = dt(row['started_at']), dt(row['restored_at'])
        dep_date = next(dt(s['created_at']) for d, s in successful if str(d['id']) == row['deployment_id'])
        if 0 <= (started - dep_date).total_seconds() <= 86400 and restored >= started:
            failed_ids.add(row['deployment_id'])
            recovery_minutes.append((restored - started).total_seconds() / 60)
    print(f'Доля неудачных изменений: {100 * len(failed_ids) / len(successful):.1f}%')
    print(f'Время восстановления (медиана): {median(recovery_minutes):.1f} мин' if recovery_minutes else 'Время восстановления: нет зарегистрированных инцидентов')
    print('Примечание: это учебный расчёт по доступной истории, не фиксированное 4-недельное окно.')


if __name__ == '__main__':
    main()
