import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = 'http://127.0.0.1:8000'
const seedTickets = [
  { id: 1042, title: 'VPN-Verbindung bricht ab', reporter: 'Mia Schmidt', priority_score: 78, priority_label: 'Critical', workflow_status: 'needs_review', evidence_status: 'unverified', created_at: 'Heute, 09:41' },
  { id: 1041, title: 'Zugriff auf Projektordner', reporter: 'Jonas Weber', priority_score: 52, priority_label: 'High', workflow_status: 'open', evidence_status: 'confirmed', created_at: 'Heute, 09:18' },
  { id: 1040, title: 'Drucker im 2. OG', reporter: 'Lea Fischer', priority_score: 24, priority_label: 'Low', workflow_status: 'open', evidence_status: 'unverified', created_at: 'Heute, 08:56' },
]

function badgeClass(value = '') {
  return value.toLowerCase().replaceAll('_', '-')
}

function App() {
  const [tickets, setTickets] = useState(seedTickets)
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('Demoansicht mit Beispieltickets. Es werden keine echten Nutzerdaten angezeigt.')
  const [form, setForm] = useState({ reporter: '', title: '', description: '', reported_priority: 'medium' })

  useEffect(() => {
    if (!live) return
    let active = true
    setLoading(true)
    fetch(`${API_BASE_URL}/tickets`)
      .then((response) => {
        if (!response.ok) throw new Error(`Queue konnte nicht geladen werden (${response.status}).`)
        return response.json()
      })
      .then((data) => { if (active) { setTickets(Array.isArray(data) ? data : data.tickets ?? []); setNotice('Live-API verbunden.') } })
      .catch((error) => { if (active) setNotice(`${error.message} Backend unter ${API_BASE_URL} starten oder Demoansicht verwenden.`) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [live])

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  async function submitTicket(event) {
    event.preventDefault()
    const payload = { ...form, title: form.title.trim(), reporter: form.reporter.trim(), description: form.description.trim() }
    if (live) {
      setLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/tickets`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        if (!response.ok) throw new Error(`Ticket konnte nicht erstellt werden (${response.status}).`)
        const created = await response.json()
        setTickets((current) => [created, ...current].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)))
        setNotice('Ticket wurde über die Live-API erstellt.')
      } catch (error) { setNotice(`${error.message} Ticket wurde nicht gespeichert.`) }
      finally { setLoading(false) }
    } else {
      const created = { ...payload, id: Date.now(), priority_score: payload.reported_priority === 'high' ? 61 : payload.reported_priority === 'low' ? 24 : 39, priority_label: payload.reported_priority === 'high' ? 'High' : payload.reported_priority === 'low' ? 'Low' : 'Medium', workflow_status: 'open', evidence_status: 'unverified', created_at: 'Gerade eben' }
      setTickets((current) => [created, ...current].sort((a, b) => b.priority_score - a.priority_score))
      setNotice('Mockticket erstellt. In der Demoansicht wird nichts an ein Backend gesendet.')
    }
    setForm({ reporter: '', title: '', description: '', reported_priority: 'medium' })
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#queue" aria-label="QueueGuard Startseite"><span className="brand-mark">Q</span><span>queueguard<small>IT SERVICE DESK</small></span></a>
        <p className="nav-caption">WORKSPACE</p>
        <a className="nav-item selected" href="#queue"><span>▦</span> Ticket Queue <b>{tickets.length}</b></a>
        <a className="nav-item" href="#new-ticket"><span>＋</span> Ticket erstellen</a>
        <div className="sidebar-bottom"><div className="secure-note"><span>✳</span><div><strong>Policy Engine aktiv</strong><small>Deterministische Prüfungen</small></div></div><div className="profile"><span className="avatar">AD</span><div><strong>Demo Workspace</strong><small>Keine Anmeldung aktiv</small></div><span className="dots">···</span></div></div>
      </aside>

      <section className="main-area" id="queue">
        <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <strong>Ticket Queue</strong></div><div className="top-actions"><span className={`connection ${live ? 'live' : ''}`}><i />{live ? 'Live API' : 'Mock-Modus'}</span><button className="mode-toggle" type="button" onClick={() => setLive((value) => !value)}>{live ? 'Demo verwenden' : 'API verbinden'}</button><span className="help">?</span><span className="avatar small-avatar">JD</span></div></header>
        <div className="content">
          <div className="page-heading"><div><p className="eyebrow">ÜBERSICHT <span>·</span> SAMSTAG, 21. NOVEMBER</p><h1>Ticket Queue</h1><p className="subtitle">Alle IT-Anfragen auf einen Blick. Priorisiert nach Dringlichkeit und Evidenz.</p></div><button className="primary-button" onClick={() => document.getElementById('reporter')?.focus()}>＋ <span>Neues Ticket</span></button></div>
          <div className="notice" role="status"><span>ⓘ</span>{notice}</div>
          <div className="metrics"><article><span className="metric-icon purple">▦</span><div><small>OFFENE TICKETS</small><strong>{tickets.length.toString().padStart(2, '0')}</strong></div><span className="metric-tail">Aktuell</span></article><article><span className="metric-icon orange">◷</span><div><small>KRITISCH</small><strong>{tickets.filter((ticket) => ticket.priority_label === 'Critical').length.toString().padStart(2, '0')}</strong></div><span className="metric-tail alert">Prüfung nötig</span></article><article><span className="metric-icon green">✓</span><div><small>BESTÄTIGTE EVIDENZ</small><strong>{tickets.filter((ticket) => ticket.evidence_status === 'confirmed').length.toString().padStart(2, '0')}</strong></div><span className="metric-tail">Verifiziert</span></article></div>
          <div className="workspace-grid">
            <section className="queue-card"><div className="card-heading"><div><h2>Aktuelle Anfragen</h2><p>Nach Priorität sortiert</p></div><button className="filter-button" onClick={() => setTickets([...tickets].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)))}>⇅ <span>Priorität</span></button></div><div className="table-scroll"><table><thead><tr><th>TICKET</th><th>PRIORITÄT</th><th>STATUS</th><th>EVIDENZ</th><th>ERSTELLT</th></tr></thead><tbody>{tickets.map((ticket) => <tr key={ticket.id}><td><div className="ticket-title">{ticket.title}</div><div className="ticket-meta">#{ticket.id} <span>·</span> {ticket.reporter || 'Unbekannt'}</div></td><td><span className={`priority ${badgeClass(ticket.priority_label)}`}><i />{ticket.priority_label ?? 'Unbewertet'}</span><small className="score">Score {ticket.priority_score ?? '–'}</small></td><td><span className={`status ${badgeClass(ticket.workflow_status)}`}>{ticket.workflow_status === 'needs_review' ? 'Prüfung nötig' : ticket.workflow_status ?? 'Offen'}</span></td><td><span className={`evidence ${badgeClass(ticket.evidence_status)}`}><i />{ticket.evidence_status === 'confirmed' ? 'Bestätigt' : 'Ungeprüft'}</span></td><td className="date-cell">{ticket.created_at ?? 'Gerade eben'}</td></tr>)}</tbody></table>{loading && <p className="empty-state">Wird geladen …</p>}{!tickets.length && !loading && <p className="empty-state">Noch keine Tickets vorhanden.</p>}</div><footer className="table-footer">Zeige <strong>{tickets.length}</strong> Tickets <span>Queue aktualisieren <button aria-label="Queue aktualisieren" onClick={() => setLive(true)}>↻</button></span></footer></section>
            <section className="form-card" id="new-ticket"><div className="form-heading"><span className="form-icon">＋</span><div><h2>Ticket melden</h2><p>Beschreibe dein Anliegen.</p></div></div><form onSubmit={submitTicket}><label htmlFor="reporter">Dein Name</label><input id="reporter" name="reporter" value={form.reporter} onChange={updateField} placeholder="z. B. Alex Müller" maxLength="120" required /><label htmlFor="title">Betreff</label><input id="title" name="title" value={form.title} onChange={updateField} placeholder="Worum geht es?" maxLength="200" required /><label htmlFor="description">Beschreibung</label><textarea id="description" name="description" value={form.description} onChange={updateField} placeholder="Was ist passiert? Was hast du bereits versucht?" maxLength="5000" rows="4" required /><div className="form-row"><label htmlFor="reported_priority">Dringlichkeit</label><select id="reported_priority" name="reported_priority" value={form.reported_priority} onChange={updateField}><option value="low">Niedrig</option><option value="medium">Normal</option><option value="high">Hoch</option></select></div><button className="submit-button" type="submit" disabled={loading}>{loading ? 'Bitte warten …' : 'Ticket einreichen'} <span>→</span></button><p className="privacy">ⓘ Die gemeldete Dringlichkeit ist ein Hinweis. Die Priorisierung erfolgt separat.</p></form></section>
          </div>
          <footer className="page-footer"><span>QueueGuard <b>·</b> Sichere IT-Unterstützung</span><span><i /> Alle Systeme betriebsbereit</span></footer>
        </div>
      </section>
    </main>
  )
}

export default App
