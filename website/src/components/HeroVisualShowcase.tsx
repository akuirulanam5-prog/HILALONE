import { useState } from "react";
import { Moon, SunMedium } from "lucide-react";

export function HeroVisualShowcase() {
  const [nightMode, setNightMode] = useState(false);

  const shot1600 = nightMode
    ? "/screenshots/processing-result-night-1600.webp"
    : "/screenshots/processing-result-dark-1600.webp";
  const shot800 = nightMode
    ? "/screenshots/processing-result-night-800.webp"
    : "/screenshots/processing-result-dark-800.webp";
  const iconWebp = "/branding/hilalone-icon-standard-96.webp";

  return (
    <figure className={`hero-visual${nightMode ? " hero-visual--night" : ""}`}>
      <div className="hero-visual__topbar">
        <div className="hero-visual__identity">
          <img
            className="hero-visual__mini-icon"
            src={iconWebp}
            alt=""
            width={22}
            height={22}
          />
          <span className="hero-visual__mode-label">
            {nightMode ? "NIGHT VISION RED" : "STANDARD DARK"}
          </span>
          <span className="hero-visual__status-pill">Data Uji Sintetis</span>
        </div>

        <div className="theme-toggle-group" role="group" aria-label="Pratinjau tema antarmuka desktop">
          <button
            type="button"
            className={`theme-toggle-btn${!nightMode ? " is-active" : ""}`}
            aria-pressed={!nightMode}
            onClick={() => setNightMode(false)}
          >
            <SunMedium size={14} aria-hidden="true" />
            <span>Dark</span>
          </button>
          <button
            type="button"
            className={`theme-toggle-btn${nightMode ? " is-active" : ""}`}
            aria-pressed={nightMode}
            onClick={() => setNightMode(true)}
          >
            <Moon size={14} aria-hidden="true" />
            <span>Night Red</span>
          </button>
        </div>
      </div>

      <div className="hero-visual__screen">
        <img
          src={shot1600}
          srcSet={`${shot800} 800w, ${shot1600} 1600w`}
          sizes="(max-width: 900px) 100vw, 680px"
          alt={
            nightMode
              ? "Tangkapan layar antarmuka desktop HILALONE dalam tema Night Vision Red memakai data uji sintetis"
              : "Tangkapan layar antarmuka desktop HILALONE dalam tema Standard Dark memakai data uji sintetis"
          }
          width={1600}
          height={900}
          fetchPriority="high"
        />
      </div>

      <figcaption className="hero-visual__caption">
        <span>Antarmuka Desktop PySide6 (Windows)</span>
        <span>Contoh pemrosesan memakai data uji sintetis, bukan observasi nyata</span>
      </figcaption>
    </figure>
  );
}
