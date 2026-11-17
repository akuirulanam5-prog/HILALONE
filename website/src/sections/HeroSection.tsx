import { Compass, Download, FileCheck2, Layers, ShieldCheck, Telescope } from "lucide-react";
import { HeroVisualShowcase } from "../components/HeroVisualShowcase";
import { HERO_HIGHLIGHTS, HERO_PILLARS } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

const PILLAR_ICONS = {
  readonly: ShieldCheck,
  "no-align": Layers,
  "split-output": FileCheck2,
} as const;

export function HeroSection() {
  return (
    <section id="beranda" className="hero">
      <div className="container">
        <div className="hero-frame">
          <div className="hero__grid">
            <div className="hero__copy">
              <div className="hero__meta">
                <Telescope size={15} aria-hidden="true" />
                <span>
                  {siteConfig.appName} v{siteConfig.version} · {siteConfig.platform}
                </span>
              </div>

              <h1 id="konten-judul" className="hero__title" tabIndex={-1}>
                Pengolahan Citra Astronomi untuk{" "}
                <span className="hero__title-accent">Observasi Hilal</span>
              </h1>

              <p className="hero__desc">
                Perangkat lunak desktop Windows untuk tim rukyat, peneliti, dan mahasiswa falak guna
                membaca, memvalidasi, menumpuk, dan mengekspor citra pengamatan secara terstruktur.
              </p>

              <blockquote className="hero__philosophy">
                &ldquo;{siteConfig.philosophy}&rdquo;
              </blockquote>

              <div className="hero__actions">
                <a href="#unduh" className="btn btn--primary">
                  <Download size={18} aria-hidden="true" />
                  <span>Unduh HILALONE v{siteConfig.version}</span>
                </a>
                <a href="#fitur" className="btn btn--navy-outline">
                  <Compass size={18} aria-hidden="true" />
                  <span>Lihat Fitur &amp; Antarmuka</span>
                </a>
              </div>

              <dl className="hero__highlights" aria-label={`Ringkasan teknis versi ${siteConfig.version}`}>
                {HERO_HIGHLIGHTS.map((item) => (
                  <div key={item.label} className="highlight-stat">
                    <dt className="highlight-stat__label">{item.label}</dt>
                    <dd className="highlight-stat__value">{item.value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="hero__visual-col">
              <HeroVisualShowcase />
            </div>
          </div>
        </div>

        {/* Strip 3 pilar inti di bawah hero (Blok 1 referensi layout) */}
        <ul className="hero-pillars" aria-label="Pilar utama desain ilmiah">
          {HERO_PILLARS.map((pillar) => {
            const IconComp = PILLAR_ICONS[pillar.id];
            return (
              <li key={pillar.id} className="hero-pillar">
                <div className="hero-pillar__icon-box" aria-hidden="true">
                  <IconComp size={20} />
                </div>
                <div className="hero-pillar__body">
                  <h2 className="hero-pillar__title">{pillar.title}</h2>
                  <p className="hero-pillar__desc">{pillar.summary}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
