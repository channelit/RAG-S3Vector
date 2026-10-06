import { useEffect, useRef, useState } from 'react'
import 'altcha' // registers the <altcha-widget> web component
import flagImg from '@uswds/uswds/img/us_flag_small.png'
import dotGovImg from '@uswds/uswds/img/icon-dot-gov.svg'
import httpsImg from '@uswds/uswds/img/icon-https.svg'
// Seal and wordmark served locally as SVG (seal traced from the public-domain artwork) — no external image hosts.
import CBP_SEAL from './assets/cbp-seal.svg'
import cbpWordmark from './assets/cbp-wordmark-white.svg'
// Social icons as used in the ace.cbp.gov footer
import facebookIcon from './assets/social/facebook.svg'
import twitterIcon from './assets/social/twitter.svg'
import youtubeIcon from './assets/social/youtube.svg'
import flickrIcon from './assets/social/flickr.svg'
import instagramIcon from './assets/social/instagram.svg'
import linkedinIcon from './assets/social/linkedin.svg'
import emailIcon from './assets/social/email.svg'
// Rules of Behavior text, kept as plain text so it can be edited without touching the UI code
import rulesOfBehaviorText from './rules-of-behavior.txt?raw'


function GovBanner() {
  const [expanded, setExpanded] = useState(false)
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
              aria-expanded={expanded}
              aria-controls="gov-banner-default"
              onClick={() => setExpanded((v) => !v)}
            >
              <span className="usa-banner__button-text">Here's how you know</span>
            </button>
          </div>
        </header>
        <div
          className="usa-banner__content usa-accordion__content"
          id="gov-banner-default"
          hidden={!expanded}
        >
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

// Footer content mirrored from the ace.cbp.gov footer.
const CBP_FOOTER_NAV = [
  ['Travel', 'https://www.cbp.gov/travel'],
  ['Trade', 'https://www.cbp.gov/trade'],
  ['Border Security', 'https://www.cbp.gov/border-security'],
  ['Newsroom', 'https://www.cbp.gov/newsroom'],
  ['About CBP', 'https://www.cbp.gov/about'],
  ['Careers', 'https://www.cbp.gov/careers'],
  ['Employee Resources', 'https://www.cbp.gov/employee-resources'],
]

const CBP_SOCIAL = [
  { label: 'Facebook', href: 'https://www.facebook.com/CBPgov', icon: facebookIcon },
  { label: 'Twitter/X', href: 'https://twitter.com/cbp', icon: twitterIcon },
  { label: 'YouTube', href: 'https://www.youtube.com/channel/UCVRj-aUsXBrlM8elk3zmLvw', icon: youtubeIcon },
  { label: 'Flickr', href: 'https://www.flickr.com/photos/cbpphotos/', icon: flickrIcon },
  { label: 'Instagram', href: 'https://www.instagram.com/cbpgov/', icon: instagramIcon },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/company/customs-and-border-protection', icon: linkedinIcon },
  { label: 'Email', href: 'https://public.govdelivery.com/accounts/USDHSCBP/subscriber/new', icon: emailIcon },
]

// One array per column, as laid out on ACE at desktop width.
const CBP_FOOTER_LINKS = [
  [
    ['Accessibility', 'https://www.cbp.gov/site-policy-notices/accessibility'],
    ['Accountability', 'https://www.cbp.gov/newsroom/publications/performance-accountability-financial'],
    ['DHS Components', 'https://www.cbp.gov/dhs-component-websites'],
    ['FOIA', 'https://www.cbp.gov/site-policy-notices/foia'],
  ],
  [
    ['Forms', 'https://www.cbp.gov/newsroom/publications/forms'],
    ['Inspector General', 'https://www.oig.dhs.gov/'],
    ['No FEAR Act', 'https://www.cbp.gov/about/eeo-diversity/no-fear-act'],
    ['Privacy', 'https://www.cbp.gov/site-policy-notices/privacy-policy'],
  ],
  [
    ['Site Policies', 'https://www.cbp.gov/site-policy-notices'],
    ['The White House', 'https://www.whitehouse.gov/'],
    ['USA.gov', 'https://www.usa.gov/'],
  ],
  [
    ['Vulnerability Disclosure Program', 'https://www.cbp.gov/document/directives/vulnerability-disclosure-program-policy-and-rules-engagement'],
  ],
]

/** ace.cbp.gov-style footer: cbp.gov section links, then the CBP wordmark with
 *  social links, then the USWDS identifier in ACE blue with the policy links. */
function SiteFooter() {
  return (
    <>
      <footer className="usa-footer usa-footer--medium ace-footer">
        <div className="usa-footer__primary-section">
          <nav className="usa-footer__nav" aria-label="Footer navigation">
            <ul className="ace-footer__nav-list">
              {CBP_FOOTER_NAV.map(([label, href]) => (
                <li key={href} className="usa-footer__primary-content">
                  <a className="usa-footer__primary-link" href={href}>{label}</a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
        <div className="usa-footer__secondary-section">
          <div className="grid-container ace-footer__brand">
            <a href="https://www.cbp.gov" className="ace-wordmark">
              <img className="ace-wordmark__seal" src={CBP_SEAL} alt="" />
              <span className="ace-wordmark__text">U.S. Customs and<br />Border Protection</span>
            </a>
            <div>
              <ul className="ace-footer__social" aria-label="CBP social media">
                {CBP_SOCIAL.map((s) => (
                  <li key={s.href}>
                    <a className="usa-social-link" href={s.href} target="_blank" rel="noopener" title={s.label}>
                      <img className="usa-social-link__icon" src={s.icon} alt={s.label} />
                    </a>
                  </li>
                ))}
              </ul>
              <p className="ace-footer__contact-link">
                <a href="https://www.cbp.gov/about/contact">Contact CBP</a>
              </p>
            </div>
          </div>
        </div>
      </footer>
      <div className="usa-identifier ace-identifier">
        <section className="usa-identifier__section usa-identifier__section--masthead" aria-label="Agency identifier">
          <div className="usa-identifier__container">
            <div className="usa-identifier__logos">
              <a href="https://www.cbp.gov" className="usa-identifier__logo">
                <img className="usa-identifier__logo-img" src={CBP_SEAL} alt="CBP seal" role="img" />
              </a>
            </div>
            <section className="usa-identifier__identity" aria-label="Agency description">
              <p className="usa-identifier__identity-domain">CBP.gov</p>
              <p className="usa-identifier__identity-disclaimer">
                An official website of the <a href="https://www.dhs.gov/">U.S. Department of Homeland Security</a>
              </p>
            </section>
          </div>
        </section>
        <nav className="usa-identifier__section ace-identifier__links" aria-label="Important links">
          <div className="usa-identifier__container">
            <div className="ace-identifier__columns">
              {CBP_FOOTER_LINKS.map((column, i) => (
                <ul key={i}>
                  {column.map(([label, href]) => (
                    <li key={href}><a href={href}>{label}</a></li>
                  ))}
                </ul>
              ))}
            </div>
          </div>
        </nav>
      </div>
    </>
  )
}

/** ace.cbp.gov-style header: navy bar with the CBP wordmark and the app name. */
function SiteHeader() {
  return (
    <header className="usa-header ace-header">
      <div className="ace-header__inner">
        <a href="https://www.cbp.gov" className="ace-header__logo">
          <img src={cbpWordmark} alt="U.S. Customs and Border Protection. CBP.gov home" />
        </a>
        <span className="ace-header__title">CSMS Intelligent Retrieval and Compliance Assistant</span>
      </div>
    </header>
  )
}

/** ALTCHA proof-of-work captcha. The backend decides whether it is on
 *  (/api/config → altcha.enabled) and the widget fetches challenges from the
 *  backend's own same-origin relative path (altcha.challenge_url), where the
 *  backend creates them itself with the altcha library. The solved payload is
 *  exchanged once for a session token (see App), so the widget is only shown
 *  until the first successful verification. */
function AltchaCaptcha({ challengeUrl, onPayload, resetKey }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onStateChange = (ev) => {
      const { state, payload } = ev.detail || {}
      onPayload(state === 'verified' && payload ? payload : null)
    }
    el.addEventListener('statechange', onStateChange)
    return () => el.removeEventListener('statechange', onStateChange)
  }, [onPayload])

  useEffect(() => {
    // Reset after a failed token exchange so the user can solve a fresh challenge
    if (resetKey > 0 && typeof ref.current?.reset === 'function') ref.current.reset()
  }, [resetKey])

  return (
    <div className="usa-form-group margin-top-3">
      <altcha-widget
        ref={ref}
        id="altcha-widget"
        challenge={challengeUrl}
        name="altcha"
        type="checkbox"
        configuration='{"hideFooter": true, "hideLogo": true}'
      ></altcha-widget>
    </div>
  )
}

// Accepting the Rules of Behavior is remembered for the browser tab session,
// like the captcha token below. Storage can throw; the in-memory state still works.
const RULES_ACCEPTED_KEY = 'rulesOfBehaviorAccepted'

function loadRulesAccepted() {
  try {
    return sessionStorage.getItem(RULES_ACCEPTED_KEY) === '1'
  } catch { /* ignore */ }
  return false
}

function saveRulesAccepted() {
  try {
    sessionStorage.setItem(RULES_ACCEPTED_KEY, '1')
  } catch { /* ignore */ }
}

/** Rules of Behavior gate, shown until the user accepts. A native <dialog>
 *  opened with showModal() traps focus and makes the page behind it inert, and
 *  Escape is disabled, so the only way past it is ACCEPT. DECLINE swaps the
 *  rules for a notice with a way back to them. Only the text scrolls; the
 *  heading and the buttons stay in view. */
function RulesOfBehaviorModal({ onAccept }) {
  const ref = useRef(null)
  const textRef = useRef(null)
  const backRef = useRef(null)
  const [declined, setDeclined] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (el && !el.open) el.showModal()
  }, [])

  // Swapping the view removes the focused button; keep focus inside the dialog
  useEffect(() => {
    (declined ? backRef : textRef).current?.focus()
  }, [declined])

  return (
    <dialog
      ref={ref}
      className="rob-modal"
      aria-labelledby="rob-heading"
      aria-describedby="rob-hint"
      onCancel={(e) => e.preventDefault()}
      // Browsers can still close on a repeated Escape; put it straight back
      onClose={(e) => e.currentTarget.showModal()}
    >
      <h2 className="rob-modal__header" id="rob-heading">Rules of Behavior</h2>
      {declined ? (
        <div className="rob-modal__body" role="alert">
          <strong>You declined the Rules of Behavior.</strong> This application can only be used
          after you accept them. You can close this page, or go back to review and accept the rules.
        </div>
      ) : (
        <div className="rob-modal__body" ref={textRef} tabIndex={0} role="region" aria-label="Rules of Behavior text">
          {rulesOfBehaviorText.trim()}
        </div>
      )}
      <p className="rob-modal__hint" id="rob-hint">
        You must accept the rules of behavior before proceeding
      </p>
      <div className="rob-modal__footer">
        {declined ? (
          <button type="button" className="usa-button" ref={backRef} onClick={() => setDeclined(false)}>
            BACK TO RULES
          </button>
        ) : (
          <>
            <button type="button" className="usa-button usa-button--outline" onClick={() => setDeclined(true)}>
              DECLINE
            </button>
            <button type="button" className="usa-button" onClick={onAccept}>
              ACCEPT
            </button>
          </>
        )}
      </div>
    </dialog>
  )
}

// The captcha session token lives in sessionStorage so one solve covers the
// whole browser tab session, reloads included. Storage can throw (private mode,
// blocked site data); the in-memory state still works then.
const CAPTCHA_TOKEN_KEY = 'altchaSessionToken'

function loadCaptchaToken() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(CAPTCHA_TOKEN_KEY) || 'null')
    if (saved?.token && saved.expires_at * 1000 > Date.now() + 30_000) return saved
  } catch { /* ignore */ }
  return null
}

function saveCaptchaToken(value) {
  try {
    if (value) sessionStorage.setItem(CAPTCHA_TOKEN_KEY, JSON.stringify(value))
    else sessionStorage.removeItem(CAPTCHA_TOKEN_KEY)
  } catch { /* ignore */ }
}

function App() {
  const [query, setQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // null until /api/config answers; then {enabled, challenge_url}
  const [altchaConfig, setAltchaConfig] = useState(null)
  // {token, expires_at} from /api/altcha/verify; covers every query until it expires
  const [captchaToken, setCaptchaTokenState] = useState(loadCaptchaToken)
  const [captchaVerifying, setCaptchaVerifying] = useState(false)
  const [altchaResetKey, setAltchaResetKey] = useState(0)
  const [rulesAccepted, setRulesAccepted] = useState(loadRulesAccepted)

  const acceptRules = () => {
    saveRulesAccepted()
    setRulesAccepted(true)
  }

  const setCaptchaToken = (value) => {
    saveCaptchaToken(value)
    setCaptchaTokenState(value)
  }

  // Widget solved: trade the one-time payload for a session token
  const onAltchaPayload = async (payload) => {
    if (!payload || !altchaConfig?.verify_url) return
    setCaptchaVerifying(true)
    try {
      const res = await fetch(altchaConfig.verify_url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ altcha: payload }),
      })
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
      const data = await res.json()
      setCaptchaToken({ token: data.token, expires_at: data.expires_at })
      setError('')
    } catch (e) {
      setError(`Captcha verification failed (${e.message})`)
      setAltchaResetKey((k) => k + 1)
    } finally {
      setCaptchaVerifying(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetch('/api/config')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`${res.status}`))))
      .then((data) => { if (!cancelled) setAltchaConfig(data.altcha ?? { enabled: false }) })
      .catch((e) => {
        if (cancelled) return
        setAltchaConfig({ enabled: false })
        setError(`Could not load site configuration (${e.message})`)
      })
    return () => { cancelled = true }
  }, [])

  const captchaRequired = altchaConfig?.enabled === true
  const captchaValid = !!captchaToken && captchaToken.expires_at * 1000 > Date.now()
  const captchaPending = altchaConfig === null || (captchaRequired && !captchaValid)

  const ask = async () => {
    if (!query.trim() || captchaPending) return
    setLoading(true)
    setError('')
    setAnswer('')
    setSources([])

    const body = { query }
    if (dateFrom) body.date_from = dateFrom
    if (dateTo) body.date_to = dateTo
    if (captchaRequired) body.captcha_token = captchaToken.token

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const text = await res.text()
        // Session expired or rejected: show the captcha again
        if (captchaRequired && (res.status === 403 || res.status === 400)) setCaptchaToken(null)
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

      <SiteHeader />

      <main id="main-content" className="usa-section">
        <div className="grid-container">
          <div className="grid-row grid-gap">
            <div className="tablet:grid-col-10 tablet:grid-offset-1 desktop:grid-col-8 desktop:grid-offset-2">

              <h1 className="font-heading-xl margin-bottom-2">CSMS AI Assistant</h1>
              <p className="usa-intro">
                Search CSMS documents using natural language. Results are filtered and sourced exclusively from uploaded content.
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
                  aria-describedby="query-hint ai-notice"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="Ask a question about CSMS documents…"
                />
                <p className="ai-notice" id="ai-notice">
                  <svg className="ai-notice__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
                  </svg>
                  AI-generated content may be inaccurate. Human review is mandatory before using or sharing this information.
                </p>
              </div>

              <fieldset className="usa-fieldset margin-top-3">
                <legend className="usa-legend">
                  Filter by document date range
                  <span className="usa-hint display-block margin-top-05">
                    Only CSMS messages published within this range will be used as sources. Leave blank to search all documents.
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

              {captchaRequired && !captchaValid && (
                <AltchaCaptcha
                  challengeUrl={altchaConfig.challenge_url}
                  onPayload={onAltchaPayload}
                  resetKey={altchaResetKey}
                />
              )}

              <button
                className="usa-button margin-top-3"
                onClick={ask}
                disabled={loading || captchaPending || captchaVerifying}
                type="button"
              >
                {loading ? 'Searching…' : 'Submit Query'}
              </button>
              {captchaRequired && !captchaValid && !loading && (
                <span className="usa-hint display-block margin-top-1">
                  Complete the verification above to enable the Submit button.
                </span>
              )}

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
                    {sources.map((s, i) => {
                      // Backend returns {label, url}; tolerate plain strings too.
                      const label = typeof s === 'string' ? s : s.label
                      const url = typeof s === 'string' ? null : s.url
                      return (
                        <li key={`${label}-${i}`} className="margin-bottom-05">
                          {url ? (
                            <a className="usa-link usa-link--external" href={url} target="_blank" rel="noopener noreferrer">
                              {label}
                              <span className="usa-sr-only"> (opens in a new tab)</span>
                            </a>
                          ) : (
                            label
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}

            </div>
          </div>
        </div>
      </main>

      <SiteFooter />

      {!rulesAccepted && <RulesOfBehaviorModal onAccept={acceptRules} />}
    </>
  )
}

export default App
