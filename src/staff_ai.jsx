import React, {useEffect, useState} from 'react';
import {api} from './api';

// Панель ИИ-подбора для сотрудников: переключатель без остановки сайта, мониторинг, переданные вопросы.
export default function AiPanel({canToggle}) {
  const [stats, setStats] = useState(null), [handoffs, setHandoffs] = useState([]), [error, setError] = useState('');
  async function load() {
    try { const [s, h] = await Promise.all([api('/admin/ai/stats'), api('/admin/ai/handoffs')]); setStats(s); setHandoffs(h) }
    catch (e) { setError(e.message) }
  }
  useEffect(() => { load() }, []);
  async function toggle() {
    try { await api('/admin/ai', {method: 'PATCH', body: JSON.stringify({enabled: !stats.enabled})}); load() }
    catch (e) { setError(e.message) }
  }
  const pct = x => x == null ? '—' : Math.round(x * 100) + '%';
  return <div className="staff-ai">
    {error && <p className="staff-error">{error}</p>}
    {stats && <>
      <div className="staff-card ai-switch">
        <div><b>ИИ-подбор питомца</b><p>{stats.enabled ? 'Включён: рекомендации формирует облачная модель с проверкой ограничений.' : 'Отключён: посетители видят подбор по правилам с уведомлением.'}</p></div>
        {canToggle && <button className={stats.enabled ? 'staff-danger' : 'staff-primary'} onClick={toggle}>{stats.enabled ? 'Отключить ИИ' : 'Включить ИИ'}</button>}
      </div>
      <div className="staff-stats">
        {[['Запросов подбора', stats.requests], ['Ответила модель', pct(stats.ai_share)], ['Резервный режим', pct(stats.fallback_share)],
          ['Отказ / уточнение', pct(stats.refusal_share)], ['Среднее время', stats.avg_latency_ms + ' мс'],
          ['Заявок из рекомендаций', stats.applications_from_recommendations], ['Конверсия в заявку', pct(stats.conversion)]]
          .map(([k, v]) => <div className="staff-stat" key={k}><span>{k}</span><b>{v}</b></div>)}
      </div>
    </>}
    <h3>Вопросы, переданные сотруднику</h3>
    <table className="staff-table"><thead><tr><th>#</th><th>Дата</th><th>Пользователь</th><th>Вопрос</th></tr></thead>
      <tbody>{handoffs.map(h => <tr key={h.id}><td>{h.id}</td><td>{h.created_at.slice(0, 16).replace('T', ' ')}</td><td>{h.email}</td><td>{h.message || '—'}</td></tr>)}</tbody></table>
    {!handoffs.length && <p className="muted">Пока нет переданных вопросов.</p>}
  </div>;
}
