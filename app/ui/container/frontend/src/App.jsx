import { useEffect, useRef, useState } from 'react'
import flagImg from '@uswds/uswds/img/us_flag_small.png'
import dotGovImg from '@uswds/uswds/img/icon-dot-gov.svg'
import httpsImg from '@uswds/uswds/img/icon-https.svg'
import closeImg from '@uswds/uswds/img/usa-icons/close.svg'
import searchImg from '@uswds/uswds/img/usa-icons-bg/search--white.svg'
import cbpWordmark from './assets/cbp-wordmark-white.svg'
// Seals served locally as SVG (CBP seal traced from the public-domain artwork) — no external image hosts.
import CBP_SEAL from './assets/cbp-seal.svg'
import DHS_SEAL from './assets/dhs-seal.svg'
// Social icons copied from the cbp.gov theme (circular, single-colour)
import xIcon from './assets/social/x.svg'
import facebookIcon from './assets/social/facebook.svg'
import instagramIcon from './assets/social/instagram.svg'
import flickrIcon from './assets/social/flickr.svg'
import truthSocialIcon from './assets/social/truth-social.svg'
import youtubeIcon from './assets/social/youtube.svg'
import linkedinIcon from './assets/social/linkedin.svg'
import emailIcon from './assets/social/email.svg'


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

// Primary sections of cbp.gov, mirrored from its live header.
const CBP_NAV = [
  { label: 'Travel', href: 'https://www.cbp.gov/travel' },
  { label: 'Trade', href: 'https://www.cbp.gov/trade' },
  { label: 'Border Security', href: 'https://www.cbp.gov/border-security' },
  { label: 'Newsroom', href: 'https://www.cbp.gov/newsroom' },
  { label: 'About CBP', href: 'https://www.cbp.gov/about' },
  { label: 'Careers', href: 'https://careers.cbp.gov/s/' },
  { label: 'Employee Resources', href: 'https://www.cbp.gov/employee-resources' },
]

// Official CBP channels and footer links, mirrored from the cbp.gov footer.
const CBP_SOCIAL = [
  { label: 'X', href: 'https://x.com/cbp', icon: xIcon },
  { label: 'Facebook', href: 'https://www.facebook.com/CBPgov', icon: facebookIcon },
  { label: 'Instagram', href: 'https://www.instagram.com/cbpgov', icon: instagramIcon },
  { label: 'Flickr', href: 'https://www.flickr.com/photos/cbpphotos', icon: flickrIcon },
  { label: 'Truth Social', href: 'https://truthsocial.com/@cbpgov', icon: truthSocialIcon },
  { label: 'YouTube', href: 'https://www.youtube.com/channel/UCVRj-aUsXBrlM8elk3zmLvw', icon: youtubeIcon },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/company/customs-and-border-protection', icon: linkedinIcon },
  { label: 'Email Updates', href: 'https://public.govdelivery.com/accounts/USDHSCBP/subscriber/new', icon: emailIcon },
]

const CBP_FOOTER_LINKS = [
  [
    ['About CBP', 'https://www.cbp.gov/about'],
    ['Section 508 Accessibility', 'https://www.cbp.gov/site-policy-notices/accessibility'],
    ['Accountability', 'https://www.cbp.gov/newsroom/accountability-and-transparency'],
    ['DHS Components', 'https://www.dhs.gov/operational-and-support-components'],
    ['Forms', 'https://www.cbp.gov/newsroom/publications/forms'],
  ],
  [
    ['Freedom of Information Act (FOIA)', 'https://www.cbp.gov/site-policy-notices/foia'],
    ['Inspector General', 'https://www.oig.dhs.gov/'],
    ['No FEAR Act', 'https://www.cbp.gov/about/eeo/no-fear-act'],
    ['Vulnerability Disclosure Program', 'https://www.cbp.gov/document/directives/vulnerability-disclosure-program-policy-and-rules-engagement'],
    ['Privacy', 'https://www.cbp.gov/site-policy-notices/privacy-policy'],
  ],
  [
    ['Contact Us', 'https://www.cbp.gov/about/contact'],
    ['Site Policies', 'https://www.cbp.gov/site-policy-notices'],
    ['The White House', 'https://www.whitehouse.gov/'],
    ['USA.gov', 'https://www.usa.gov/'],
    ['Freedom 250', 'https://www.cbp.gov/250'],
  ],
]

/** cbp.gov-style footer: white band with the CBP wordmark + social links, then
 *  a black band carrying the DHS identifier and three columns of links. */
function SiteFooter() {
  return (
    <footer className="usa-footer usa-footer--medium cbp-footer">
      <div className="usa-footer__primary-section cbp-footer__top">
        <div className="grid-container cbp-footer__top-inner">
          <a href="https://www.cbp.gov" className="cbp-footer__wordmark">
            <img className="cbp-footer__seal" src={CBP_SEAL} alt="" />
            <span className="cbp-footer__wordmark-text">U.S. Customs and<br />Border Protection</span>
          </a>
          <ul className="cbp-footer__social" aria-label="CBP social media">
            {CBP_SOCIAL.map((s) => (
              <li key={s.href}>
                <a className="usa-social-link cbp-social-link" href={s.href} target="_blank" rel="noopener" title={`CBP ${s.label}`}>
                  <img src={s.icon} alt={s.label} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="usa-footer__secondary-section cbp-footer__bottom">
        <div className="grid-container">
          <section className="usa-identifier__section usa-identifier__section--masthead" aria-label="Agency identifier">
            <div className="usa-identifier__container">
              <div className="usa-identifier__logos">
                <a href="https://www.dhs.gov" className="usa-identifier__logo">
                  <img className="usa-identifier__logo-img" src={DHS_SEAL} alt="U.S. Department of Homeland Security seal" role="img" />
                </a>
              </div>
              <div className="usa-identifier__identity" aria-label="Agency description">
                <p className="usa-identifier__identity-domain">CBP.gov</p>
                <p className="usa-identifier__identity-disclaimer">
                  An official website of the <a href="https://www.dhs.gov">U.S. Department of Homeland Security</a>
                </p>
              </div>
            </div>
          </section>
          <nav className="cbp-footer__links grid-row grid-gap-lg" aria-label="Footer links">
            {CBP_FOOTER_LINKS.map((column, i) => (
              <ul key={i} className="tablet:grid-col-4">
                {column.map(([label, href]) => (
                  <li key={href}><a href={href}>{label}</a></li>
                ))}
              </ul>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  )
}

/** cbp.gov-style extended header: dark bar, seal wordmark, site search, primary links.
 *  USWDS JS is not loaded in this app, so the mobile menu toggle is handled here. */
function SiteHeader() {
  const [navOpen, setNavOpen] = useState(false)
  const menuBtnRef = useRef(null)
  const closeBtnRef = useRef(null)

  const openNav = () => setNavOpen(true)
  const closeNav = () => setNavOpen(false)

  useEffect(() => {
    if (navOpen) {
      closeBtnRef.current?.focus()
      const onKey = (e) => { if (e.key === 'Escape') closeNav() }
      document.addEventListener('keydown', onKey)
      return () => document.removeEventListener('keydown', onKey)
    }
    menuBtnRef.current?.focus({ preventScroll: true })
  }, [navOpen])

  return (
    <>
      <div className={`usa-overlay${navOpen ? ' is-visible' : ''}`} onClick={closeNav}></div>
      <header className="usa-header usa-header--extended cbp-header">
        <div className="usa-navbar">
          <div className="usa-logo cbp-wordmark" id="extended-logo">
            <a href="https://www.cbp.gov" className="cbp-wordmark__link">
              <img
                className="cbp-wordmark__img"
                src={cbpWordmark}
                alt="U.S. Customs and Border Protection, U.S. Department of Homeland Security. CBP.gov home"
              />
            </a>
            <span className="cbp-wordmark__app">CSMS Intelligent Retrieval and Compliance Assistant</span>
          </div>
          <button
            type="button"
            className="usa-menu-btn"
            ref={menuBtnRef}
            aria-expanded={navOpen}
            aria-controls="primary-nav"
            onClick={openNav}
          >
            Menu
          </button>
        </div>
        <nav aria-label="Primary navigation" className={`usa-nav${navOpen ? ' is-visible' : ''}`} id="primary-nav">
          <div className="usa-nav__inner">
            <button type="button" className="usa-nav__close" ref={closeBtnRef} onClick={closeNav}>
              <img src={closeImg} role="img" alt="Close" />
            </button>
            <ul className="usa-nav__primary usa-accordion">
              {CBP_NAV.map((item) => (
                <li key={item.href} className="usa-nav__primary-item">
                  <a href={item.href} className="usa-nav__link"><span>{item.label}</span></a>
                </li>
              ))}
            </ul>
            <div className="usa-nav__secondary">
              <section aria-label="Search CBP.gov">
                <form
                  className="usa-search usa-search--small cbp-search"
                  role="search"
                  action="https://www.cbp.gov/search"
                  method="get"
                >
                  <label className="usa-sr-only" htmlFor="cbp-search-field">Search CBP.gov</label>
                  <input
                    className="usa-input"
                    id="cbp-search-field"
                    type="search"
                    name="query"
                    placeholder="Search CBP.gov"
                  />
                  <button className="usa-button" type="submit">
                    <img src={searchImg} className="usa-search__submit-icon" alt="Search" />
                  </button>
                </form>
              </section>
            </div>
          </div>
        </nav>
      </header>
    </>
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

      <SiteHeader />

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
    </>
  )
}

export default App
