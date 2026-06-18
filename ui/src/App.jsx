import { useState, useEffect, useRef } from 'react'
import './index.css'

const CFG_ITEMS = [
  { key: 'bait_pos',       label: 'Bait button',    kind: 'pos'    },
  { key: 'water_pos',      label: 'Water button',   kind: 'pos'    },
  { key: 'deto_pos',       label: 'Deto button',    kind: 'pos'    },
  { key: 'first_fish_pos', label: 'First fish',     kind: 'pos'    },
  { key: 'recycle_pos',    label: 'Recycle button', kind: 'pos'    },
  { key: 'uranium_img',    label: 'Uranium region', kind: 'region' },
  { key: 'splash_img',     label: 'Splash region',  kind: 'region' },
  { key: 'nothing_img',    label: 'Nothing notif',  kind: 'region' },
  { key: 'emptier_img',    label: 'Inv. emptier',   kind: 'region' },
  { key: 'empty_fish_img', label: 'Empty fish',     kind: 'region' },
  { key: 'number_bbox',    label: 'Recycle number', kind: 'region' },
]

const api = () => window.pywebview?.api

export default function App() {
  const [status,     setStatus]     = useState({ text: 'Idle — configure positions below', color: 'var(--gt-green)' })
  const [instr,      setInstr]      = useState('Click Set on any row, or Setup All.')
  const [cfg,        setCfg]        = useState({})
  const [logs,       setLogs]       = useState([])
  const [running,    setRunning]    = useState(false)
  const [capturing,  setCapturing]  = useState(false)
  const [paused,     setPaused]     = useState(false)
  const [fish,       setFish]       = useState(0)
  const [elapsed,    setElapsed]    = useState('00:00:00')
  const [logOpen,    setLogOpen]    = useState(false)
  const [unreadLogs, setUnreadLogs] = useState(0)
  const logRef = useRef(null)

  useEffect(() => {
    window.__push = (ev) => {
      if (ev.type === 'status')     setStatus({ text: ev.text, color: ev.color })
      if (ev.type === 'instr')      setInstr(ev.text)
      if (ev.type === 'log') {
        setLogs(l => [...l.slice(-199), ev.msg])
        setUnreadLogs(u => u + 1)
      }
      if (ev.type === 'cfg_update') setCfg(c => ({ ...c, [ev.key]: { text: ev.text, ok: ev.ok } }))
      if (ev.type === 'state') {
        setRunning(ev.running)
        setCapturing(ev.capturing)
        setPaused(ev.paused)
        setFish(ev.fish)
        setElapsed(ev.elapsed)
      }
    }
  }, [])

  useEffect(() => {
    if (logOpen && logRef.current)
      logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs, logOpen])

  const openLog  = () => { setLogOpen(true);  setUnreadLogs(0) }
  const closeLog = () => { setLogOpen(false); setUnreadLogs(0) }

  const allSet = CFG_ITEMS.every(i => cfg[i.key]?.ok)
  const busy   = running || capturing

  return (
    <>
      {/* ── Log overlay — mounted only when open ── */}
      {logOpen && <div className="gt-overlay-bg" onClick={closeLog} aria-hidden="true" />}
      {logOpen && <div className="gt-overlay" role="dialog" aria-label="Log" aria-modal="true">
        <div className="gt-panel" style={{ borderRadius: '4px 4px 0 0', margin: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <div className="gt-panel-title" style={{ borderBottom: 'none', marginBottom: 0, paddingBottom: 0 }}>
              &gt;&gt; LOG
            </div>
            <button
              className="gt-btn gt-btn-red"
              onClick={closeLog}
              aria-label="Close log"
              style={{ fontSize: '16px', padding: '2px 10px 4px' }}
            >
              [X]
            </button>
          </div>
          <div
            ref={logRef}
            className="gt-sunken"
            style={{ height: '260px', overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: '1px' }}
          >
            {logs.length === 0
              ? <span className="gt-log-empty">Waiting for events...</span>
              : logs.map((l, i) => <span key={i} className="gt-log-line">&gt; {l}</span>)
            }
          </div>
        </div>
      </div>}

      {/* ── Main layout ── */}
      <div style={{
        minHeight: '100vh',
        maxWidth: '480px',
        margin: '0 auto',
        padding: '14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}>

        {/* Title + LOG button */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', paddingBottom: '2px' }}>
          <div>
            <div style={{
              fontFamily: "'VT323', monospace",
              fontSize: '40px',
              lineHeight: 1,
              letterSpacing: '3px',
              color: 'var(--gt-amber)',
              textShadow: '2px 2px 0 rgba(0,0,0,0.7), 0 0 24px rgba(220,160,50,0.25)',
            }}>
              Growfisher
            </div>
            <div style={{
              fontFamily: "'VT323', monospace",
              fontSize: '16px',
              letterSpacing: '1.5px',
              color: 'var(--gt-text-muted)',
            }}>
              Growtopia fishing assistant - Uranium edition
            </div>
          </div>
          <button
            className="gt-btn gt-btn-blue"
            onClick={openLog}
            aria-label="Open log"
            style={{ fontSize: '16px', padding: '4px 12px 6px', marginTop: '6px', position: 'relative' }}
          >
            LOG{unreadLogs > 0 && (
              <span style={{
                position: 'absolute',
                top: '-6px',
                right: '-6px',
                background: 'var(--gt-red)',
                color: '#fff',
                fontSize: '12px',
                fontFamily: "'VT323', monospace",
                lineHeight: 1,
                padding: '1px 4px',
                borderRadius: '3px',
                boxShadow: '0 2px 0 var(--gt-red-dk)',
                pointerEvents: 'none',
              }}>
                {unreadLogs > 99 ? '99+' : unreadLogs}
              </span>
            )}
          </button>
        </div>

        {/* Status */}
        <div className="gt-panel">
          <div className="gt-panel-title">&gt;&gt; STATUS</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <span style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              flexShrink: 0,
              backgroundColor: status.color,
              boxShadow: `0 0 7px ${status.color}`,
            }} />
            <span style={{ fontFamily: "'VT323', monospace", fontSize: '20px', color: status.color }}>
              {status.text}
            </span>
          </div>
          <div style={{ fontFamily: "'VT323', monospace", fontSize: '17px', color: 'var(--gt-text-muted)', paddingLeft: '20px' }}>
            {instr}
          </div>
        </div>

        {/* Configuration */}
        <div className="gt-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <div style={{ fontFamily: "'VT323', monospace", fontSize: '13px', letterSpacing: '2.5px', color: 'var(--gt-amber)', textShadow: '0 1px 3px rgba(0,0,0,0.7)' }}>
              &gt;&gt; CONFIGURATION
            </div>
            <button disabled={busy} onClick={() => api()?.start_setup_all()} className="gt-btn gt-btn-blue">
              Setup All
            </button>
          </div>
          <div style={{ borderTop: '2px solid var(--gt-bevel-lo)', paddingTop: '4px' }}>
            {CFG_ITEMS.map(({ key, label, kind }) => (
              <div key={key} className="gt-row">
                <span style={{ fontFamily: "'VT323', monospace", fontSize: '17px', color: 'var(--gt-text-muted)', width: '130px', flexShrink: 0 }}>
                  {label}
                </span>
                <span style={{
                  fontFamily: "'VT323', monospace",
                  fontSize: '16px',
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  color: cfg[key]?.ok ? 'var(--gt-green)' : 'var(--gt-text-muted)',
                  opacity: cfg[key]?.ok ? 1 : 0.55,
                  textShadow: cfg[key]?.ok ? '0 0 6px var(--gt-green)' : 'none',
                }}>
                  {cfg[key]?.text ?? '-- not set --'}
                </span>
                <button disabled={busy} onClick={() => api()?.capture_item(key, kind)} className="gt-btn gt-btn-blue">
                  Set
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="gt-panel">
          <div className="gt-panel-title">&gt;&gt; STATS</div>
          <div style={{ display: 'flex', gap: '32px', fontFamily: "'VT323', monospace", fontSize: '22px' }}>
            <span>Fish: <span style={{ color: 'var(--gt-amber)', textShadow: '0 0 8px rgba(220,160,50,0.4)' }}>{fish}</span></span>
            <span>Time: <span style={{ color: 'var(--gt-amber)', textShadow: '0 0 8px rgba(220,160,50,0.4)' }}>{elapsed}</span></span>
          </div>
        </div>

        {/* Controls */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            disabled={!allSet || running}
            onClick={() => api()?.start_fishing()}
            className="gt-btn gt-btn-green"
            style={{ flex: 1, fontSize: '22px', paddingTop: '8px', paddingBottom: '10px' }}
          >START</button>
          <button
            disabled={!running}
            onClick={() => api()?.toggle_pause()}
            className={`gt-btn ${paused ? 'gt-btn-green' : 'gt-btn-orange'}`}
            style={{ flex: 1, fontSize: '22px', paddingTop: '8px', paddingBottom: '10px' }}
          >{paused ? 'RESUME' : 'PAUSE'}</button>
          <button
            disabled={!running}
            onClick={() => api()?.stop_fishing()}
            className="gt-btn gt-btn-red"
            style={{ flex: 1, fontSize: '22px', paddingTop: '8px', paddingBottom: '10px' }}
          >STOP</button>
        </div>

        {/* Hint */}
        <div style={{
          fontFamily: "'VT323', monospace",
          fontSize: '15px',
          letterSpacing: '1px',
          color: 'var(--gt-text-muted)',
          textAlign: 'center',
          paddingBottom: '4px',
          opacity: 0.7,
        }}>
          CTRL: capture &nbsp;|&nbsp; ESC: stop &nbsp;|&nbsp; P: pause
        </div>

      </div>
    </>
  )
}
