
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import requests

REPO = "kokanoavaamina93/PetHome"
PROJECT_ID = "prj_hwuS0OhqJA8vmOygxcOsxyq1EiWB"
TEAM_SLUG = "fariza-amina"

GH_TOKEN = os.environ["GH_TOKEN"]
VERCEL_TOKEN = os.environ["VERCEL_TOKEN"]

NOW = datetime.now(timezone.utc)
START = NOW - timedelta(days=28)
START_MS = int(START.timestamp() * 1000)

GH_HEADERS = {"Authorization": f"Bearer {GH_TOKEN}"}
VERCEL_HEADERS = {"Authorization": f"Bearer {VERCEL_TOKEN}"}


def api_get(url, headers, params=None):
    response = requests.get(
        url, headers=headers, params=params, timeout=30
    )
    response.raise_for_status()
    return response.json()


def parse_date(value):
    if not value:
        return None
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def get_deployments():
    result = []
    until = int(NOW.timestamp() * 1000)

    while True:
        data = api_get(
            "https://api.vercel.com/v6/deployments",
            VERCEL_HEADERS,
            {
                "projectId": PROJECT_ID,
                "slug": TEAM_SLUG,
                "limit": 100,
                "since": START_MS,
                "until": until,
            },
        )

        page = data.get("deployments", [])
        result.extend(page)

        next_page = data.get("pagination", {}).get("next")
        if not page or next_page is None:
            break

        if int(next_page) >= until:
            raise RuntimeError("Ошибка пагинации Vercel")

        until = int(next_page)

    return result


def deployment_time(dep):
    timestamp = dep.get("ready") or dep.get("createdAt")

    if timestamp is None:
        return None

    return datetime.fromtimestamp(
        int(timestamp) / 1000, timezone.utc
    )


def get_commit_date(sha):
    if not sha:
        return None

    url = f"https://api.github.com/repos/{REPO}/commits/{sha}"

    response = requests.get(
        url,
        headers=GH_HEADERS,
        timeout=30
    )

    if response.status_code == 404:
        print(
            f"Коммит {sha[:7]} не найден в GitHub. "
            "Пропускаем его."
        )
        return None

    response.raise_for_status()
    data = response.json()

    return parse_date(
        data["commit"]["committer"]["date"]
    )


def read_incidents():
    path = Path("scripts/incidents.csv")

    if not path.exists():
        return []

    with path.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


def main():
    deployments = get_deployments()

    ready = [
        d for d in deployments
        if d.get("readyState", d.get("state")) == "READY"
    ]

    preview = [
        d for d in ready
        if d.get("target") != "production"
    ]

    production = [
        d for d in ready
        if d.get("target") == "production"
    ]

    print("PetHome — метрики DORA")
    print("Период:", START.date(), "—", NOW.date())
    print("Всего получено:", len(deployments))
    print("Успешных Preview:", len(preview))
    print("Успешных Production:", len(production))

    # 1. Частота развёртываний
    frequency = len(preview) / 4

    print(
        f"Частота Preview: {frequency:.2f} в неделю"
    )

    # 2. Время доставки изменений
    lead_hours = []
    commit_cache = {}

    for dep in preview:
        sha = (
            dep.get("meta", {}).get("githubCommitSha")
            or dep.get("gitSource", {}).get("sha")
        )

        deployed = deployment_time(dep)

        if not sha or not deployed:
            continue

        if sha not in commit_cache:
            commit_cache[sha] = get_commit_date(sha)

        committed = commit_cache[sha]

        if committed and deployed >= committed:
            lead_hours.append(
                (deployed - committed).total_seconds() / 3600
            )

    lead_time = (
        median(lead_hours)
        if lead_hours else None
    )

    if lead_time is not None:
        print(f"Lead Time: {lead_time:.2f} часов")
    else:
        print(
            "Lead Time: недостаточно данных о коммитах"
        )

    # 3 и 4. Инциденты
    incidents = read_incidents()

    valid_ids = {
        str(d.get("uid", d.get("id"))): d
        for d in preview
    }

    failed_ids = set()
    recovery_minutes = []
    repair_hours = 0.0

    for row in incidents:
        dep_id = row.get(
            "deployment_id", ""
        ).strip()

        if dep_id not in valid_ids:
            continue

        started = parse_date(
            row.get("started_at")
        )

        restored = parse_date(
            row.get("restored_at")
        )

        deployed = deployment_time(
            valid_ids[dep_id]
        )

        if not started or not restored or not deployed:
            continue

        delay = (
            started - deployed
        ).total_seconds()

        duration = (
            restored - started
        ).total_seconds()

        if 0 <= delay <= 86400 and duration >= 0:
            failed_ids.add(dep_id)

            recovery_minutes.append(
                duration / 60
            )

            repair_hours += duration / 3600

    cfr = (
        100 * len(failed_ids) / len(preview)
        if preview else None
    )

    mttr = (
        median(recovery_minutes)
        if recovery_minutes else None
    )

    print(
        "Доля неудачных изменений:",
        f"{cfr:.1f}%" if cfr is not None
        else "нет данных"
    )

    print(
        "Время восстановления:",
        f"{mttr:.1f} мин" if mttr is not None
        else "нет зарегистрированных инцидентов"
    )

    print(
        f"Длительность инцидентов: {repair_hours:.2f} ч"
    )

    metrics = {
        "project": "PetHome",
        "period_start": START.isoformat(),
        "period_end": NOW.isoformat(),
        "deployment_frequency_per_week": frequency,
        "lead_time_hours": lead_time,
        "change_failure_rate_percent": cfr,
        "time_to_restore_minutes": mttr,
        "incident_duration_hours": repair_hours,
        "preview_deployments": len(preview),
        "production_deployments": len(production),
        "matched_commits": len(lead_hours),
        "recorded_incidents": len(recovery_minutes),
    }

    Path("dora_metrics.json").write_text(
        json.dumps(
            metrics,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )

    print(
        "Результаты сохранены в dora_metrics.json"
    )


if __name__ == "__main__":
    main()
