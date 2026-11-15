import { Compass, Download, Telescope } from "lucide-react";
import { HeroVisualShowcase } from "../components/HeroVisualShowcase";
import { HERO_HIGHLIGHTS } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

export function HeroSection() {
  return (
    <section id="beranda" className="hero">
      <div className="container hero__grid">
        <div>
          <div className="hero__badge">
            <Telescope size={14} aria-hidden="true" />
            <span>
              {siteConfig.appName} v{siteConfig.version} · {siteConfig.platform}
            </span>
          </div>

          <h1 className="hero__title">
            Pengolahan Citra Astronomi untuk{" "}
            <span className="hero__title-accent">Observasi Hilal</span>
          </h1>

          <p className="hero__desc">
            HILALONE adalah perangkat lunak desktop untuk membaca, mengolah, dan
            meningkatkan citra astronomi melalui workflow pemrosesan yang
            terstruktur, transparan, dan menjaga integritas data ilmiah.
          </p>

          <blockquote className="hero__philosophy" style={{ marginInline: 0 }}>
            &ldquo;{siteConfig.philosophy}&rdquo;
          </blockquote>

          <div className="hero__actions">
            <a href="#unduh" className="btn btn--primary">
              <Download size={18} aria-hidden="true" />
              <span>Unduh HILALONE</span>
            </a>
            <a href="#fitur" className="btn btn--secondary">
              <Compass size={18} aria-hidden="true" />
              <span>Jelajahi Fitur</span>
            </a>
          </div>

          <div className="hero__highlights" aria-label="Ringkasan teknis versi 1.0.0">
            {HERO_HIGHLIGHTS.map((item) => (
              <div key={item.label}>
                <div className="highlight-stat__label">{item.label}</div>
                <div className="highlight-stat__value">{item.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <HeroVisualShowcase />
        </div>
      </div>
    </section>
  );
}
