import { useState } from 'react'

function App() {
  const [query, setQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ask = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setAnswer('')
    setSources([])

    const body = { query }
    if (dateFrom) body.date_from = dateFrom
    if (dateTo) body.date_to = dateTo

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`${res.status}: ${text}`)
      }
      const data = await res.json()
      setAnswer(data.answer ?? JSON.stringify(data, null, 2))
      setSources(Array.isArray(data.sources) ? data.sources : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') ask()
  }

  return (
    <>
      <a className="usa-skipnav" href="#main-content">Skip to main content</a>

      <header className="usa-header usa-header--basic" role="banner">
        <div className="usa-nav-container">
          <div className="usa-navbar">
            <div className="usa-logo">
              <em className="usa-logo__text">
                CSMS Intelligent Retrieval and Compliance Assistant
              </em>
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" className="usa-section">
        <div className="grid-container">
          <div className="grid-row grid-gap">
            <div className="tablet:grid-col-10 tablet:grid-offset-1 desktop:grid-col-8 desktop:grid-offset-2">

              <h1 className="font-heading-xl margin-bottom-4">CSMS Query</h1>

              <div className="usa-form-group">
                <label className="usa-label" htmlFor="query">
                  Ask a question
                </label>
                <span className="usa-hint" id="query-hint">
                  Press Ctrl+Enter or ⌘+Enter to submit
                </span>
                <textarea
                  className="usa-textarea"
                  id="query"
                  name="query"
                  aria-describedby="query-hint"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="Ask a question to the CSMS…"
                />
              </div>

              <fieldset className="usa-fieldset margin-top-3">
                <legend className="usa-legend">Filter by document date range <span className="usa-hint">(optional)</span></legend>
                <div className="grid-row grid-gap">
                  <div className="tablet:grid-col-6">
                    <div className="usa-form-group">
                      <label className="usa-label" htmlFor="date-from">From</label>
                      <input
                        className="usa-input"
                        id="date-from"
                        type="date"
                        value={dateFrom}
                        onChange={(e) => setDateFrom(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="tablet:grid-col-6">
                    <div className="usa-form-group">
                      <label className="usa-label" htmlFor="date-to">To</label>
                      <input
                        className="usa-input"
                        id="date-to"
                        type="date"
                        value={dateTo}
                        onChange={(e) => setDateTo(e.target.value)}
                        min={dateFrom || undefined}
                      />
                    </div>
                  </div>
                </div>
              </fieldset>

              <button
                className="usa-button margin-top-2"
                onClick={ask}
                disabled={loading}
                type="button"
              >
                {loading ? 'Thinking…' : 'Ask'}
              </button>

              {error && (
                <div className="usa-alert usa-alert--error margin-top-4" role="alert">
                  <div className="usa-alert__body">
                    <h4 className="usa-alert__heading">Error</h4>
                    <p className="usa-alert__text">{error}</p>
                  </div>
                </div>
              )}

              {answer && (
                <div
                  className="usa-summary-box margin-top-4"
                  role="region"
                  aria-label="Answer"
                >
                  <div className="usa-summary-box__body">
                    <h3 className="usa-summary-box__heading">Answer</h3>
                    <div className="usa-summary-box__text answer-text">
                      {answer}
                    </div>
                  </div>
                </div>
              )}

              {sources.length > 0 && (
                <div className="margin-top-3">
                  <h4 className="font-heading-xs text-base-dark margin-bottom-1">
                    Sources
                  </h4>
                  <ul className="usa-list usa-list--unstyled font-body-xs text-base">
                    {sources.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

            </div>
          </div>
        </div>
      </main>

      <footer className="usa-footer usa-footer--slim">
        <div className="usa-footer__secondary-section">
          <div className="grid-container">
            <div className="usa-footer__logo grid-row grid-gap-2">
              <div className="grid-col-auto">
                <p className="usa-footer__logo-heading">CSMS</p>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </>
  )
}

export default App
