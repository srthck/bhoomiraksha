import { useEffect, type ReactNode } from 'react'
import { ArrowRight, BarChart3, Home, Map, Users } from 'lucide-react'
import IndiaHero from './IndiaHero'
import { BrandMark, IndiaFlag } from './BrandMark'
import { Reveal } from '../motion/primitives'
import { prefetchEarth, prefetchRemoteStyle } from '../console/basemap'
import '../styles/landing.css'

/* Landing reveal schedule (ms after mount). Background layers run on CSS
   animation delays in landing.css; the copy runs on these. */
const T = { title: 1250, lede: 1400, support: 1470, cta: 1550, stats: 1700, cards: 1800 }

const NAV = ['Home', 'About', 'Features', 'Data & insights', 'Contact']

const STATS = [
  { value: '28', label: 'States' },
  { value: '8', label: 'Major hazards' },
  { value: '700K+', label: 'Habitations analysed' },
  { value: '1', label: 'Safer India' },
]

const CARDS = [
  { icon: <Map size={20} strokeWidth={1.6} />, title: 'Hazard-based', detail: 'Red zone identification' },
  { icon: <Users size={20} strokeWidth={1.6} />, title: 'Carrying capacity', detail: 'Assessment' },
  { icon: <Home size={20} strokeWidth={1.6} />, title: 'Vulnerable habitations', detail: '& relocation planning' },
  { icon: <BarChart3 size={20} strokeWidth={1.6} />, title: 'Data-driven', detail: 'Decision support' },
]

export default function Landing({ onEnter, leaving = false }: { onEnter: () => void; leaving?: boolean }) {
  // warm the basemap and the globe texture while the visitor reads, so
  // pressing Get started starts the camera on an already-painted Earth
  useEffect(() => {
    void prefetchRemoteStyle()
    prefetchEarth()
  }, [])

  const enter = () => {
    if (!leaving) onEnter()
  }

  return (
    <main className={`landing ${leaving ? 'is-leaving' : ''}`}>
      <div className="landing-sky" />
      <IndiaHero />
      <div className="landing-mountains" aria-hidden="true">
        <span className="ridge-far" />
        <span className="ridge-mid" />
        <span className="ridge-near" />
      </div>
      <div className="landing-fog" aria-hidden="true" />
      <div className="landing-scrim" aria-hidden="true" />

      <header className="landing-nav">
        <button className="brand" onClick={enter} aria-label="Bhoomi Raksha — enter the command centre">
          <BrandMark />
          <span>
            <strong>Bhoomi Raksha</strong>
            <small>Safer land · Stronger communities · A resilient India</small>
          </span>
        </button>
        <nav aria-label="Primary">
          {NAV.map((item, i) => (
            <a key={item} href={`#${item.split(' ')[0].toLowerCase()}`} aria-current={i === 0 ? 'page' : undefined}>
              {item}
            </a>
          ))}
        </nav>
        <button className="country-pill" aria-label="Region: India">
          <IndiaFlag />
          India
        </button>
      </header>

      <section className="landing-copy">
        <Reveal base={T.title - 140} className="eyebrow">Disaster resilient India</Reveal>
        <Reveal base={T.title}>
          <h1 className="landing-title">
            <span>Bhoomi</span>
            <span className="title-raksha">Raksha</span>
          </h1>
        </Reveal>
        <Reveal base={T.lede}>
          <p className="landing-lede">
            Intelligent hazard mapping, carrying capacity assessment &amp; relocation decision support system.
          </p>
        </Reveal>
        <Reveal base={T.support}>
          <p className="landing-support">
            Data-driven intelligence for safer habitations, stronger communities and a resilient tomorrow.
          </p>
        </Reveal>
        <Reveal base={T.cta}>
          <div className="landing-ctas">
            <button className="btn btn-primary" onClick={enter}>
              Get started <ArrowRight className="btn-arrow" size={17} />
            </button>
            <button className="btn btn-glass" onClick={enter}>
              <Map size={17} /> Explore map
            </button>
          </div>
        </Reveal>
        <Reveal base={T.stats}>
          <div className="landing-stats">
            {STATS.map((s) => (
              <div key={s.label}>
                <strong>{s.value}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      <Reveal base={T.stats + 90} className="landing-strap" y={10}>
        Prepared communities.
        <br />
        Safer tomorrows.
        <i className="tricolour" />
      </Reveal>

      <Reveal base={T.cards} className="landing-cards" as="footer" y={22}>
        {CARDS.map((c) => (
          <Card key={c.title} icon={c.icon} title={c.title} detail={c.detail} onClick={enter} />
        ))}
      </Reveal>

      <Reveal base={T.cards + 120} className="landing-signature" y={8}>
        Our Land
        <br />
        Our People
        <br />
        Our Responsibility
      </Reveal>

      <Reveal base={T.cards + 120} className="landing-tail" y={8}>
        A safer
        <br />
        stronger
        <br />
        resilient India
      </Reveal>
    </main>
  )
}

function Card({ icon, title, detail, onClick }: { icon: ReactNode; title: string; detail: string; onClick: () => void }) {
  return (
    <button className="cap-card" onClick={onClick}>
      {icon}
      <span>
        <strong>{title}</strong>
        <br />
        <small>{detail}</small>
      </span>
    </button>
  )
}
