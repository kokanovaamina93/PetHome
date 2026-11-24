import React, {useState} from 'react';
import {Sparkles, Send, AlertTriangle, UserRound, ArrowRight} from 'lucide-react';
import {api} from './api';

// Интеллектуальный подбор питомца (ЛЗ 12): анкета + ИИ-чат + персональные рекомендации — одна функция.
const FIELDS = [
  ['preferred_type', 'Кого ищете', [['', '—'], ['cat', 'Кошку'], ['dog', 'Собаку'], ['any', 'Не важно']]],
  ['housing', 'Жильё', [['', '—'], ['apartment', 'Квартира'], ['house', 'Частный дом']]],
  ['kids', 'Дети', [['', '—'], ['none', 'Нет'], ['under6', 'До 6 лет'], ['over6', 'Старше 6 лет']]],
  ['other_pets', 'Другие животные', [['', '—'], ['none', 'Нет'], ['cat', 'Есть кошка'], ['dog', 'Есть собака']]],
  ['time_per_day', 'Время в день', [['', '—'], ['low', 'Меньше часа'], ['medium', '1–3 часа'], ['high', 'Больше 3 часов']]],
  ['experience', 'Опыт', [['', '—'], ['none', 'Нет опыта'], ['some', 'Немного'], ['experienced', 'Большой']]],
  ['activity', 'Образ жизни', [['', '—'], ['low', 'Спокойный'], ['medium', 'Умеренный'], ['high', 'Активный']]],
  ['walks_ready', 'Готовы гулять ежедневно', [['', '—'], ['yes', 'Да'], ['no', 'Нет']]],
  ['size_pref', 'Размер', [['', '—'], ['small', 'Маленький'], ['medium', 'Средний'], ['large', 'Крупный'], ['any', 'Не важно']]],
  ['age_pref', 'Возраст', [['', '—'], ['young', 'Молодой'], ['adult', 'Взрослый'], ['senior', 'Пожилой'], ['any', 'Не важно']]],
  ['allergy', 'Аллергия в семье', [['', '—'], ['no', 'Нет'], ['yes', 'Да']]],
];

export default function Matcher({onOpen, session}) {
  const [profile, setProfile] = useState({});
  const [input, setInput] = useState('');
  const [chat, setChat] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [handoffSent, setHandoffSent] = useState(false);

  async function ask(e) {
    e?.preventDefault();
    const messages = input.trim() ? [...chat, {role: 'user', text: input.trim()}] : chat;
    setChat(messages); setInput(''); setBusy(true); setError(''); setHandoffSent(false);
    try {
      const message = messages.filter(m => m.role === 'user').map(m => m.text).join('. ');
      const r = await api('/ai/recommend', {method: 'POST', body: JSON.stringify({profile, message})});
      setResult(r);
      const reply = r.action === 'clarify' ? r.question
        : r.action === 'no_safe_match' ? 'Среди животных в приюте нет вариантов, которые точно подойдут под ваши условия. ' + (r.question || '')
        : `Подобрала ${r.items.length} ${r.items.length === 1 ? 'вариант' : 'варианта'} — посмотрите ниже.`;
      setChat([...messages, {role: 'ai', text: reply}]);
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function handoff() {
    try {
      await api('/ai/handoff', {method: 'POST', body: JSON.stringify({
        recommendation_id: result?.recommendation_id,
        message: chat.filter(m => m.role === 'user').map(m => m.text).join('. ').slice(0, 1000)})});
      setHandoffSent(true);
    } catch (err) { setError(err.message) }
  }

  return <main className="wrap section page-main matcher">
    <span className="mini-label">ПОДБОР С ИИ</span>
    <h1 className="page-title">Кто подойдёт именно вам?</h1>
    <p className="intro">Заполните анкету и расскажите о себе своими словами — помощник предложит животных из приюта и объяснит почему.</p>
    <div className="ai-banner"><Sparkles size={18}/> Рекомендации сформированы с помощью искусственного интеллекта. Совместимость и условия содержания необходимо подтвердить с сотрудником приюта.</div>
    <div className="matcher-grid">
      <form className="matcher-form" onSubmit={ask}>
        <h3>Анкета</h3>
        {FIELDS.map(([k, label, opts]) => <label key={k}>{label}
          <select value={profile[k] || ''} onChange={e => setProfile({...profile, [k]: e.target.value})}>
            {opts.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select></label>)}
        <label>Город<input value={profile.city || ''} placeholder="Например, Астана" onChange={e => setProfile({...profile, city: e.target.value})}/></label>
        <button className="primary" disabled={busy}>{busy ? 'Подбираем…' : 'Подобрать'} <ArrowRight size={17}/></button>
      </form>
      <section className="matcher-chat">
        <h3>Чат с помощником</h3>
        <div className="chat-log">
          {!chat.length && <p className="muted">Например: «Живу в квартире, работаю из дома, хочу спокойную кошку».</p>}
          {chat.map((m, i) => <div key={i} className={'bubble ' + m.role}>{m.role === 'ai' && <Sparkles size={14}/>} {m.text}</div>)}
        </div>
        <form className="chat-input" onSubmit={ask}>
          <input value={input} maxLength={1000} placeholder="Напишите о себе или ответьте на вопрос…" onChange={e => setInput(e.target.value)}/>
          <button className="primary" disabled={busy} aria-label="Отправить"><Send size={17}/></button>
        </form>
        <small className="muted">Не указывайте телефон, адрес и другие личные данные: текст обрабатывается внешним ИИ-сервисом.</small>
      </section>
    </div>
    {error && <p className="notice">{error}</p>}
    {result && <section className="matcher-results">
      {result.mode !== 'ai' && <div className="ai-banner fallback"><AlertTriangle size={18}/> {result.notice}</div>}
      {result.items.length > 0 && <div className="cards">{result.items.map(a => <article className="pet-card" key={a.id}>
        <div className="pet-image" onClick={() => onOpen(a, result.recommendation_id)}><img src={a.image_url} alt={a.name}/></div>
        <div className="pet-body"><h3>{a.name}</h3><p className="muted">{a.breed} · {a.age}</p>
          <p className="reason"><Sparkles size={14}/> {a.reason || 'Подходит по анкете'}</p>
          <button className="outline" onClick={() => onOpen(a, result.recommendation_id)}>Познакомиться и подать заявку</button></div>
      </article>)}</div>}
      {result.handoff && <div className="handoff">
        <p><UserRound size={18}/> Безопасно подобрать автоматически не получилось. Сотрудник приюта поможет лично.</p>
        {result.alternatives?.length > 0 && <p className="muted">Можно обсудить с сотрудником: {result.alternatives.map(a => a.name).join(', ')} — по ним не хватает подтверждённых данных.</p>}
        {session ? (handoffSent ? <p className="notice">Вопрос передан сотруднику приюта. Ответ придёт на {session.email}.</p>
          : <button className="primary" onClick={handoff}>Передать вопрос сотруднику</button>)
          : <p className="muted">Войдите в аккаунт, чтобы передать вопрос сотруднику.</p>}
      </div>}
    </section>}
  </main>;
}
