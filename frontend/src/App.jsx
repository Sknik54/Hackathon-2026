import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = 'http://127.0.0.1:8000'
const seedTickets = [
  { id: 1042, title: 'VPN-Verbindung bricht ab', reporter: 'Mia Schmidt', priority_score: 78, priority_label: 'Critical', workflow_status: 'needs_review', evidence_status: 'unverified', reasoning: 'Demo: Ungeprüfte Hinweise auf ein Verbindungsproblem. Manuelle Prüfung nötig.', created_at: 'Heute, 09:41' },
  { id: 1041, title: 'Zugriff auf Projektordner', reporter: 'Jonas Weber', priority_score: 52, priority_label: 'High', workflow_status: 'open', evidence_status: 'confirmed', reasoning: 'Demo: Eingeschränkter Zugriff auf einen Projektordner.', created_at: 'Heute, 09:18' },
  { id: 1040, title: 'Drucker im 2. OG', reporter: 'Lea Fischer', priority_score: 24, priority_label: 'Low', workflow_status: 'open', evidence_status: 'unverified', reasoning: 'Demo: Einzelne Druckeranfrage ohne bestätigte Störung.', created_at: 'Heute, 08:56' },
]

function badgeClass(value = '') {
  return String(value).toLowerCase().replaceAll('_', '-')
}

async function requestJson(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? `: ${body.detail}` : ''
    } catch { /* The API may return an empty or non-JSON error body. */ }
    const error = new Error(`HTTP ${response.status}${detail}`)
    error.status = response.status
    throw error
  }
  return response.status === 204 ? null : response.json()
}

function App() {
  const [tickets, setTickets] = useState(seedTickets)
  const [rowsSource, setRowsSource] = useState('demo')
  const [live, setLive] = useState(false)
  const [apiState, setApiState] = useState('mock')
  const [loading, setLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [notice, setNotice] = useState('Demoansicht: Die angezeigten Beispieltickets sind erfunden und werden nicht an ein Backend gesendet.')
  const [noticeTone, setNoticeTone] = useState('info')
  const [form, setForm] = useState({ reporter: '', title: '', description: '', reported_priority: 'medium' })
  const [monitoring, setMonitoring] = useState([])
  const [monitoringState, setMonitoringState] = useState('idle')
  const [monitoringMessage, setMonitoringMessage] = useState('Monitoring wird nach erfolgreicher API-Verbindung geladen.')
  const [audit, setAudit] = useState([])
  const [auditState, setAuditState] = useState('idle')
  const [auditMessage, setAuditMessage] = useState('')
  const [pendingAction, setPendingAction] = useState('')

  useEffect(() => {
    if (!live) return undefined
    let active = true
    requestJson('/tickets')
      .then((data) => {
        if (!active) return
        const rows = Array.isArray(data) ? data : data?.tickets
        if (!Array.isArray(rows)) throw new Error('Unerwartetes Antwortformat von GET /tickets.')
        setTickets(rows)
        setRowsSource('api')
        setApiState('connected')
        setNotice(`Backend verbunden. ${rows.length} Ticket${rows.length === 1 ? '' : 's'} aus GET /tickets geladen.`)
        setNoticeTone('success')
        loadMonitoring(() => active)
      })
      .catch((error) => {
        if (!active) return
        setApiState('error')
        setNotice(`GET /tickets ist fehlgeschlagen (${error.message}). Es wurde keine neue Live-Antwort bestätigt; der Datentyp der sichtbaren Einträge ist oben gekennzeichnet.`)
        setNoticeTone('error')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [live, refreshKey])

  async function loadMonitoring(isActive = () => true) {
    setMonitoringState('loading')
    setMonitoringMessage('Monitoring wird geladen …')
    try {
      const data = await requestJson('/monitoring')
      if (!isActive()) return
      if (!Array.isArray(data?.services)) throw new Error('Unerwartetes Antwortformat von GET /monitoring.')
      setMonitoring(data.services)
      setMonitoringState('ready')
      setMonitoringMessage('Monitoring-Daten vom Backend geladen. Statuswerte können simuliert sein.')
    } catch (error) {
      if (!isActive()) return
      setMonitoring([])
      setMonitoringState(error.status === 404 ? 'missing' : 'error')
      setMonitoringMessage(error.status === 404
        ? 'GET /monitoring ist im Backend noch nicht verfügbar.'
        : `Monitoring konnte nicht geladen werden (${error.message}).`)
    }
  }

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  function toggleMode() {
    if (live) {
      setLive(false)
      setTickets(seedTickets)
      setRowsSource('demo')
      setApiState('mock')
      setMonitoringState('idle')
      setMonitoring([])
      setAudit([])
      setAuditState('idle')
      setAuditMessage('')
      setLoading(false)
      setNotice('Demoansicht: Die angezeigten Beispieltickets sind erfunden und werden nicht an ein Backend gesendet.')
      setNoticeTone('info')
    } else {
      setApiState('connecting')
      setLoading(true)
      setNotice(`Verbinde mit ${API_BASE_URL} …`)
      setNoticeTone('info')
      setLive(true)
    }
  }

  async function submitTicket(event) {
    event.preventDefault()
    const payload = { ...form, title: form.title.trim(), reporter: form.reporter.trim(), description: form.description.trim() }
    setLoading(true)
    let success = false
    try {
      if (live) {
        const created = await requestJson('/tickets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        setTickets((current) => [created, ...current].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)))
        setRowsSource('api')
        setApiState('connected')
        setNotice('Ticket wurde erfolgreich über POST /tickets erstellt.')
        setNoticeTone('success')
      } else {
        const created = {
          ...payload,
          id: `demo-${Date.now()}`,
          priority_score: payload.reported_priority === 'high' ? 61 : payload.reported_priority === 'low' ? 24 : 39,
          priority_label: payload.reported_priority === 'high' ? 'High' : payload.reported_priority === 'low' ? 'Low' : 'Medium',
          workflow_status: 'open',
          evidence_status: 'unverified',
          reasoning: 'Demoantwort: Für dieses Beispiel wurde keine Backend-Analyse ausgeführt.',
          created_at: 'Gerade eben',
        }
        setTickets((current) => [created, ...current].sort((a, b) => b.priority_score - a.priority_score))
        setRowsSource('demo')
        setNotice('Mockticket erstellt. Es wurde nichts an ein Backend gesendet.')
        setNoticeTone('info')
      }
      success = true
    } catch (error) {
      setNotice(error.status === 404
        ? 'POST /tickets ist im Backend nicht verfügbar (404). Das Ticket wurde nicht gespeichert.'
        : `Ticket konnte nicht erstellt werden (${error.message}). Das Ticket wurde nicht gespeichert.`)
      setNoticeTone('error')
    } finally {
      setLoading(false)
    }
    if (success) setForm({ reporter: '', title: '', description: '', reported_priority: 'medium' })
  }

  function refreshQueue() {
    if (!live) {
      setNotice('Demoansicht aktiv. Die Beispieltickets werden lokal angezeigt.')
      setNoticeTone('info')
      return
    }
    setLoading(true)
    if (apiState !== 'connected') {
      setApiState('connecting')
      setNotice(`Verbinde mit ${API_BASE_URL} …`)
      setNoticeTone('info')
    }
    setRefreshKey((key) => key + 1)
  }

  async function changeMonitoring(service) {
    const nextStatus = service.status === 'offline' ? 'online' : 'offline'
    const actionKey = `monitoring-${service.service_id}`
    setPendingAction(actionKey)
    try {
      const updated = await requestJson(`/demo/monitoring/${encodeURIComponent(service.service_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus, affected_users: nextStatus === 'offline' ? 250 : 0 }),
      })
      if (updated?.service_id) {
        setMonitoring((current) => current.map((item) => item.service_id === updated.service_id ? updated : item))
      } else {
        await loadMonitoring()
      }
      setNotice(`Demo-Monitoring für ${service.service_id} wurde auf ${nextStatus} gesetzt.`)
      setNoticeTone('success')
    } catch (error) {
      setMonitoringMessage(error.status === 404
        ? 'Der Demo-Schalter POST /demo/monitoring/{service_id} ist im Backend noch nicht verfügbar.'
        : `Demo-Monitoring konnte nicht geändert werden (${error.message}).`)
      setMonitoringState(error.status === 404 ? 'missing' : 'error')
    } finally {
      setPendingAction('')
    }
  }

  async function reanalyzeTicket(ticket) {
    const actionKey = `reanalyze-${ticket.id}`
    setPendingAction(actionKey)
    try {
      const updated = await requestJson(`/tickets/${encodeURIComponent(ticket.id)}/reanalyze`, { method: 'POST' })
      setTickets((current) => current.map((item) => item.id === ticket.id ? updated : item)
        .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)))
      setNotice(`Ticket #${ticket.id} wurde erneut analysiert.`)
      setNoticeTone('success')
    } catch (error) {
      setNotice(error.status === 404
        ? 'Die Reanalyse-Route POST /tickets/{ticket_id}/reanalyze ist im Backend noch nicht verfügbar.'
        : `Ticket #${ticket.id} konnte nicht neu analysiert werden (${error.message}).`)
      setNoticeTone('error')
    } finally {
      setPendingAction('')
    }
  }

  async function showAudit() {
    setAuditState('loading')
    setAuditMessage('Audit-Ereignisse werden geladen …')
    try {
      const data = await requestJson('/audit')
      const rows = Array.isArray(data) ? data : data?.events
      if (!Array.isArray(rows)) throw new Error('Unerwartetes Antwortformat von GET /audit.')
      setAudit(rows)
      setAuditState('ready')
      setAuditMessage(`${rows.length} Audit-Ereignisse geladen.`)
    } catch (error) {
      setAudit([])
      setAuditState(error.status === 404 ? 'missing' : 'error')
      setAuditMessage(error.status === 404
        ? 'GET /audit ist im Backend noch nicht verfügbar.'
        : `Audit konnte nicht geladen werden (${error.message}).`)
    }
  }

  const usingDemoRows = rowsSource === 'demo'
  const connectionLabel = !live ? 'Mock-Modus' : apiState === 'connected' ? 'Backend verbunden' : apiState === 'connecting' ? 'Verbinde …' : apiState === 'error' ? 'API-Fehler' : 'Live-Modus'
  const ticketCount = tickets.length.toString().padStart(2, '0')

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#queue" aria-label="QueueGuard Startseite"><span className="brand-mark">Q</span><span>queueguard<small>IT SERVICE DESK</small></span></a>
        <p className="nav-caption">WORKSPACE</p>
        <a className="nav-item selected" href="#queue"><span>▦</span> Ticket Queue <b>{tickets.length}</b></a>
        <a className="nav-item" href="#new-ticket"><span>＋</span> Ticket erstellen</a>
        <div className="sidebar-bottom"><div className="secure-note"><span>ⓘ</span><div><strong>Keine Anmeldung aktiv</strong><small>Demo ohne Authentifizierung</small></div></div><div className="profile"><span className="avatar">QG</span><div><strong>QueueGuard Demo</strong><small>{live ? 'Backend-Modus' : 'Mock-Modus'}</small></div><span className="dots">···</span></div></div>
      </aside>

      <section className="main-area" id="queue">
        <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <strong>Ticket Queue</strong></div><div className="top-actions"><span className={`connection ${apiState === 'connected' ? 'live' : apiState === 'error' ? 'error' : ''}`}><i />{connectionLabel}</span><button className="mode-toggle" type="button" onClick={toggleMode}>{live ? 'Demo verwenden' : 'API verbinden'}</button><span className="help">?</span><span className="avatar small-avatar">QG</span></div></header>
        <div className="content">
          <div className="page-heading"><div><p className="eyebrow">QUEUEGUARD <span>·</span> TICKETÜBERSICHT</p><h1>Ticket Queue</h1><p className="subtitle">Anfragen mit Priorität, Evidenz und Backend-Begründung.</p></div><button className="primary-button" onClick={() => document.getElementById('reporter')?.focus()}>＋ <span>Neues Ticket</span></button></div>
          <div className={`notice ${noticeTone}`} role="status">{tickets.some((ticket) => String(ticket.reasoning ?? "").startsWith("OFFLINE-DEMO:")) && <strong>OFFLINE-DEMO: Diese Queue enth?lt simulierte Agentenantworten. </strong>}<span>{noticeTone === 'error' ? '⚠' : noticeTone === 'success' ? '✓' : 'ⓘ'}</span>{notice}</div>
          <div className="metrics"><article><span className="metric-icon purple">▦</span><div><small>{usingDemoRows ? 'TICKETS · DEMO FALLS API NICHT VERBUNDEN' : 'TICKETS AUS DEM BACKEND'}</small><strong>{ticketCount}</strong></div><span className="metric-tail">{usingDemoRows ? 'Beispieldaten' : 'API-Antwort'}</span></article><article><span className="metric-icon orange">◷</span><div><small>PRÜFUNG NÖTIG</small><strong>{tickets.filter((ticket) => ticket.workflow_status === 'needs_review').length.toString().padStart(2, '0')}</strong></div><span className="metric-tail alert">needs_review</span></article><article><span className="metric-icon green">✓</span><div><small>BESTÄTIGTE EVIDENZ</small><strong>{tickets.filter((ticket) => ticket.evidence_status === 'confirmed').length.toString().padStart(2, '0')}</strong></div><span className="metric-tail">Ticketdaten</span></article></div>
          <div className="workspace-grid">
            <section className="queue-card"><div className="card-heading"><div><h2>Aktuelle Anfragen</h2><p>{usingDemoRows ? 'Demo-Beispieldaten' : 'Antwort von GET /tickets'}</p></div><div className="queue-actions"><button className="filter-button" type="button" onClick={() => setTickets((rows) => [...rows].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)))}>⇅ <span>Priorität</span></button><button className="filter-button" type="button" onClick={refreshQueue} disabled={loading} aria-label="Queue aktualisieren">↻ <span>Aktualisieren</span></button></div></div><div className="table-scroll"><table><thead><tr><th>TICKET / BEGRÜNDUNG</th><th>PRIORITÄT</th><th>STATUS</th><th>EVIDENZ</th><th>AKTION</th></tr></thead><tbody>{tickets.map((ticket) => <tr key={ticket.id}><td><div className="ticket-title">{ticket.title}</div><div className="ticket-meta">#{ticket.id} <span>·</span> {ticket.reporter || 'Meldende Person unbekannt'}</div><details className="ticket-reason"><summary>Begründung anzeigen</summary><p>{ticket.reasoning || 'Für dieses Ticket liegt keine Begründung vor.'}</p></details></td><td><span className={`priority ${badgeClass(ticket.priority_label)}`}><i />{ticket.priority_label ?? 'Unbewertet'}</span><small className="score">Score {ticket.priority_score ?? '–'}</small></td><td><span className={`status ${badgeClass(ticket.workflow_status)}`}>{ticket.workflow_status === 'needs_review' ? 'Manuelle Prüfung nötig' : ticket.workflow_status ?? 'Offen'}</span></td><td><span className={`evidence ${badgeClass(ticket.evidence_status)}`}><i />{ticket.evidence_status === 'confirmed' ? 'Bestätigt' : ticket.evidence_status ?? 'Ungeprüft'}</span></td><td>{live && ticket.id != null && <button className="row-action" type="button" onClick={() => reanalyzeTicket(ticket)} disabled={pendingAction === `reanalyze-${ticket.id}`}>{pendingAction === `reanalyze-${ticket.id}` ? 'Läuft …' : 'Neu analysieren'}</button>}</td></tr>)}</tbody></table>{loading && <p className="empty-state">Wird geladen …</p>}{!tickets.length && !loading && <p className="empty-state">Keine Tickets in der Antwort.</p>}</div><footer className="table-footer">Zeige <strong>{tickets.length}</strong> {usingDemoRows ? 'Demo-Tickets' : 'API-Tickets'}<span>Queue <button type="button" aria-label="Queue aktualisieren" onClick={refreshQueue} disabled={loading}>↻</button></span></footer></section>
            <section className="form-card" id="new-ticket"><div className="form-heading"><span className="form-icon">＋</span><div><h2>Ticket melden</h2><p>{live ? 'Über POST /tickets an das Backend.' : 'Lokale Mock-Antwort, keine Speicherung.'}</p></div></div><form onSubmit={submitTicket}><label htmlFor="reporter">Dein Name</label><input id="reporter" name="reporter" value={form.reporter} onChange={updateField} placeholder="z. B. Alex Müller" maxLength="120" required /><label htmlFor="title">Betreff</label><input id="title" name="title" value={form.title} onChange={updateField} placeholder="Worum geht es?" maxLength="200" required /><label htmlFor="description">Beschreibung</label><textarea id="description" name="description" value={form.description} onChange={updateField} placeholder="Was ist passiert? Was hast du bereits versucht?" maxLength="5000" rows="4" required /><div className="form-row"><label htmlFor="reported_priority">Gemeldete Dringlichkeit</label><select id="reported_priority" name="reported_priority" value={form.reported_priority} onChange={updateField}><option value="low">Niedrig</option><option value="medium">Normal</option><option value="high">Hoch</option></select></div><button className="submit-button" type="submit" disabled={loading}>{loading ? 'Bitte warten …' : live ? 'An Backend senden' : 'Demo-Ticket erstellen'} <span>→</span></button><p className="privacy">Die gemeldete Dringlichkeit ist ein Hinweis. Sie ist keine Rechteprüfung.</p></form></section>
          </div>

          <section className="integration-grid" aria-label="Monitoring und Audit">
            <article className="integration-card"><div className="integration-heading"><div><h2>Monitoring</h2><p>Nur verfügbare Backend-Endpunkte werden bedient.</p></div>{live && monitoringState !== 'idle' && <span className={`mini-state ${monitoringState}`}>{monitoringState === 'ready' ? 'Geladen' : monitoringState === 'missing' ? 'Route fehlt' : monitoringState === 'loading' ? 'Lädt …' : 'Fehler'}</span>}</div><p className="integration-message">{live ? monitoringMessage : 'Im Mock-Modus gibt es keine Monitoring-Verbindung.'}</p>{monitoringState === 'ready' && <div className="service-list">{monitoring.map((service) => <div className="service-row" key={service.service_id}><span className={`service-dot ${badgeClass(service.status)}`} /><strong>{service.service_id}</strong><span>{service.status} · {service.affected_users} betroffen</span><button type="button" onClick={() => changeMonitoring(service)} disabled={pendingAction === `monitoring-${service.service_id}`}>{pendingAction === `monitoring-${service.service_id}` ? '…' : service.status === 'offline' ? 'Online setzen' : 'Offline setzen'}</button></div>)}</div>}</article>
            <article className="integration-card"><div className="integration-heading"><div><h2>Audit</h2><p>Sicherheits- und Analyseereignisse aus der API.</p></div><button className="filter-button" type="button" onClick={showAudit} disabled={!live || auditState === 'loading'}>{auditState === 'loading' ? 'Lädt …' : 'Audit laden'}</button></div><p className="integration-message">{!live ? 'Im Mock-Modus werden keine Audit-Daten vorgetäuscht.' : auditMessage || 'Audit-Ereignisse erst auf Anfrage laden.'}</p>{auditState === 'ready' && <ul className="audit-list">{audit.map((event, index) => <li key={event.id ?? index}><strong>{event.event_type ?? event.event ?? event.action ?? 'Ereignis'}</strong><span>{event.created_at ?? event.timestamp ?? ''}</span><p>{event.detail ?? event.details ?? event.message ?? event.reasoning ?? ''}</p></li>)}</ul>}</article>
          </section>
          <footer className="page-footer"><span>QueueGuard <b>·</b> Demo ohne Authentifizierung</span><span>{live ? 'Backendstatus: ' + connectionLabel : 'Mock-Daten, keine Live-Systemprüfung'}</span></footer>
        </div>
      </section>
    </main>
  )
}

export default App
