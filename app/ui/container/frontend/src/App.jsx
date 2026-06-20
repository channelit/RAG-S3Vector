import { useState } from 'react'
import flagImg from '@uswds/uswds/dist/img/us_flag_small.png'
import dotGovImg from '@uswds/uswds/dist/img/icon-dot-gov.svg'
import httpsImg from '@uswds/uswds/dist/img/icon-https.svg'

const CBP_SEAL = 'https://upload.wikimedia.org/wikipedia/commons/0/08/Seal_of_U.S._Customs_and_Border_Protection.png'
const DHS_SEAL = 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Seal_of_the_United_States_Department_of_Homeland_Security.svg/120px-Seal_of_the_United_States_Department_of_Homeland_Security.svg.png'

function GovBanner() {
  return (
    <section className="usa-banner" aria-label="Official website of the United States government">
      <div className="usa-accordion">
        <header className="usa-banner__header">
          <div className="usa-banner__inner">
            <div className="grid-col-auto">
              <img aria-hidden="true" className="usa-banner__header-flag" src={flagImg} alt="" />
            </div>
            <div className="grid-col-fill tablet:grid-col-auto" aria-hidden="true">
              <p className="usa-banner__header-text">
                An official website of the United States government
              </p>
              <p className="usa-banner__header-action">Here's how you know</p>
            </div>
            <button
              type="button"
              className="usa-accordion__button usa-banner__button"
              aria-expanded="false"
              aria-controls="gov-banner-default"
            >
              <span className="usa-banner__button-text">Here's how you know</span>
            </button>
          </div>
        </header>
        <div className="usa-banner__content usa-accordion__content" id="gov-banner-default">
          <div className="grid-row grid-gap-lg">
            <div className="usa-banner__guidance tablet:grid-col-6">
              <img className="usa-banner__icon usa-media-block__img" src={dotGovImg} role="img" alt="" aria-hidden="true" />
              <div className="usa-media-block__body">
                <p>
                  <strong>Official websites use .gov</strong><br />
                  A <strong>.gov</strong> website belongs to an official government organization in the United States.
                </p>
              </div>
            </div>
            <div className="usa-banner__guidance tablet:grid-col-6">
              <img className="usa-banner__icon usa-media-block__img" src={httpsImg} role="img" alt="" aria-hidden="true" />
              <div className="usa-media-block__body">
                <p>
                  <strong>Secure .gov websites use HTTPS</strong><br />
                  A <strong>lock</strong> or <strong>https://</strong> means you've safely connected to the .gov website. Share sensitive information only on official, secure websites.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

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

      <GovBanner />

      <div className="usa-overlay"></div>

      <header className="usa-header usa-header--basic" role="banner">
        <div className="usa-nav-container">
          <div className="usa-navbar">
            <div className="usa-logo cbp-logo">
              <img
                src={CBP_SEAL}
                alt="U.S. Customs and Border Protection seal"
                className="cbp-logo__seal"
              />
              <div className="cbp-logo__text">
                <span className="cbp-logo__agency">U.S. Customs and Border Protection</span>
                <span className="cbp-logo__subagency">U.S. Department of Homeland Security</span>
                <em className="usa-logo__text cbp-logo__app">
                  CSMS Intelligent Retrieval and Compliance Assistant
                </em>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" className="usa-section">
        <div className="grid-container">
          <div className="grid-row grid-gap">
            <div className="tablet:grid-col-10 tablet:grid-offset-1 desktop:grid-col-8 desktop:grid-offset-2">

              <h1 className="font-heading-xl margin-bottom-2">Document Query</h1>
              <p className="usa-intro">
                Search ingested CSMS documents using natural language. Results are filtered through Bedrock Guardrails and sourced exclusively from uploaded content.
              </p>

              <div className="usa-form-group margin-top-4">
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
                  placeholder="Ask a question about CSMS documents…"
                />
              </div>

              <fieldset className="usa-fieldset margin-top-3">
                <legend className="usa-legend">
                  Filter by document date range
                  <span className="usa-hint display-block margin-top-05">
                    Only documents uploaded within this range will be used as sources. Leave blank to search all documents.
                  </span>
                </legend>
                <div className="grid-row grid-gap">
                  <div className="tablet:grid-col-6">
                    <div className="usa-form-group">
                      <label className="usa-label" htmlFor="date-from">From date</label>
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
                      <label className="usa-label" htmlFor="date-to">To date</label>
                      <input
                        className="usa-input"
                        id="date-to"
                        type="date"
                        value={dateTo}
                        min={dateFrom || undefined}
                        onChange={(e) => setDateTo(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              </fieldset>

              <button
                className="usa-button margin-top-3"
                onClick={ask}
                disabled={loading}
                type="button"
              >
                {loading ? 'Searching…' : 'Submit Query'}
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
                <div className="usa-summary-box margin-top-4" role="region" aria-label="Query answer">
                  <div className="usa-summary-box__body">
                    <h3 className="usa-summary-box__heading">Answer</h3>
                    <div className="usa-summary-box__text answer-text">{answer}</div>
                  </div>
                </div>
              )}

              {sources.length > 0 && (
                <div className="margin-top-3">
                  <h4 className="font-heading-xs text-base-dark margin-bottom-1">Sources</h4>
                  <ul className="usa-list usa-list--unstyled font-body-xs text-base">
                    {sources.map((s) => (
                      <li key={s} className="margin-bottom-05">{s}</li>
                    ))}
                  </ul>
                </div>
              )}

            </div>
          </div>
        </div>
      </main>

      <footer className="usa-footer usa-footer--slim">
        <div className="usa-footer__primary-section">
          <div className="usa-footer__primary-container grid-row">
            <div className="mobile-lg:grid-col-8">
              <nav className="usa-footer__nav" aria-label="Footer navigation">
                <ul className="grid-row grid-gap">
                  <li className="mobile-lg:grid-col-6 desktop:grid-col-auto usa-footer__primary-content">
                    <a className="usa-footer__primary-link" href="https://www.cbp.gov">CBP.gov</a>
                  </li>
                  <li className="mobile-lg:grid-col-6 desktop:grid-col-auto usa-footer__primary-content">
                    <a className="usa-footer__primary-link" href="https://www.dhs.gov">DHS.gov</a>
                  </li>
                  <li className="mobile-lg:grid-col-6 desktop:grid-col-auto usa-footer__primary-content">
                    <a className="usa-footer__primary-link" href="https://www.cbp.gov/about/legal/foia">FOIA</a>
                  </li>
                  <li className="mobile-lg:grid-col-6 desktop:grid-col-auto usa-footer__primary-content">
                    <a className="usa-footer__primary-link" href="https://www.cbp.gov/about/legal/privacy-policy">Privacy Policy</a>
                  </li>
                </ul>
              </nav>
            </div>
            <div className="mobile-lg:grid-col-4">
              <address className="usa-footer__address">
                <div className="grid-row grid-gap">
                  <div className="grid-col-auto mobile-lg:grid-col-12 desktop:grid-col-auto">
                    <div className="usa-footer__contact-info">
                      <a href="https://www.cbp.gov/contact">Contact CBP</a>
                    </div>
                  </div>
                </div>
              </address>
            </div>
          </div>
        </div>
        <div className="usa-footer__secondary-section">
          <div className="grid-container">
            <div className="usa-footer__logo grid-row grid-gap-2">
              <div className="grid-col-auto">
                <img className="usa-footer__logo-img" src={CBP_SEAL} alt="" />
              </div>
              <div className="grid-col-auto">
                <p className="usa-footer__logo-heading">U.S. Customs and Border Protection</p>
              </div>
            </div>
          </div>
        </div>
      </footer>

      <div className="usa-identifier">
        <section
          className="usa-identifier__section usa-identifier__section--masthead"
          aria-label="Agency identifier"
        >
          <div className="usa-identifier__container">
            <div className="usa-identifier__logos">
              <a href="https://www.cbp.gov" className="usa-identifier__logo">
                <img
                  className="usa-identifier__logo-img"
                  src={CBP_SEAL}
                  alt="CBP seal"
                  role="img"
                />
              </a>
              <a href="https://www.dhs.gov" className="usa-identifier__logo">
                <img
                  className="usa-identifier__logo-img"
                  src={DHS_SEAL}
                  alt="DHS seal"
                  role="img"
                />
              </a>
            </div>
            <section className="usa-identifier__identity" aria-label="Agency description">
              <p className="usa-identifier__identity-domain">cbp.gov</p>
              <p className="usa-identifier__identity-disclaimer">
                An official website of{' '}
                <a href="https://www.cbp.gov">U.S. Customs and Border Protection</a>,{' '}
                <a href="https://www.dhs.gov">U.S. Department of Homeland Security</a>
              </p>
            </section>
          </div>
        </section>
        <nav
          className="usa-identifier__section usa-identifier__section--required-links"
          aria-label="Important links"
        >
          <div className="usa-identifier__container">
            <ul className="usa-identifier__required-links-list">
              <li className="usa-identifier__required-links-item">
                <a href="https://www.cbp.gov/about" className="usa-identifier__required-link usa-link">About CBP</a>
              </li>
              <li className="usa-identifier__required-links-item">
                <a href="https://www.cbp.gov/about/legal/accessibility" className="usa-identifier__required-link usa-link">Accessibility statement</a>
              </li>
              <li className="usa-identifier__required-links-item">
                <a href="https://www.cbp.gov/about/legal/foia" className="usa-identifier__required-link usa-link">FOIA requests</a>
              </li>
              <li className="usa-identifier__required-links-item">
                <a href="https://www.cbp.gov/about/legal/privacy-policy" className="usa-identifier__required-link usa-link">Privacy policy</a>
              </li>
              <li className="usa-identifier__required-links-item">
                <a href="https://www.dhs.gov/vulnerability-disclosure-policy" className="usa-identifier__required-link usa-link">Vulnerability disclosure policy</a>
              </li>
            </ul>
          </div>
        </nav>
        <section
          className="usa-identifier__section usa-identifier__section--usagov"
          aria-label="U.S. government information and services"
        >
          <div className="usa-identifier__container">
            <div className="usa-identifier__usagov-description">
              Looking for U.S. government information and services?
            </div>
            <a href="https://www.usa.gov/" className="usa-link">Visit USA.gov</a>
          </div>
        </section>
      </div>
    </>
  )
}

export default App
