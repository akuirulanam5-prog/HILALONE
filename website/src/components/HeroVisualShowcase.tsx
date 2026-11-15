import { useState } from "react";
import { Moon, SunMedium } from "lucide-react";

export function HeroVisualShowcase() {
  const [nightMode, setNightMode] = useState(false);

  const logoWebp = nightMode
    ? "/branding/hilalone-logo-night-red-512.webp"
    : "/branding/hilalone-logo-standard-512.webp";
  const logoPng = nightMode
    ? "/branding/hilalone-logo-night-red-512.png"
    : "/branding/hilalone-logo-standard-512.png";
  const previewShot = nightMode
    ? "/screenshots/processing-result-night-800.webp"
    : "/screenshots/processing-result-dark-800.webp";

  return (
    <div className={`hero-visual${nightMode ? " hero-visual--night" : ""}`}>
      <div className="hero-visual__topbar">
        <span className="hero-visual__mode-label">
          {nightMode ? "TEMA: NIGHT VISION RED" : "TEMA: STANDARD DARK"}
        </span>
        <div className="theme-pill-group" role="group" aria-label="Pratinjau tema antarmuka">
          <button
            type="button"
            className={`theme-pill${!nightMode ? " is-active" : ""}`}
            aria-pressed={!nightMode}
            onClick={() => setNightMode(false)}
          >
            <SunMedium size={12} style={{ display: "inline", marginRight: 4, verticalAlign: "-1px" }} aria-hidden="true" />
            Dark
          </button>
          <button
            type="button"
            className={`theme-pill${nightMode ? " is-active" : ""}`}
            aria-pressed={nightMode}
            onClick={() => setNightMode(true)}
          >
            <Moon size={12} style={{ display: "inline", marginRight: 4, verticalAlign: "-1px" }} aria-hidden="true" />
            Night Red
          </button>
        </div>
      </div>

      <div className="hero-visual__stage">
        <div className="orbit-ring orbit-ring--outer" aria-hidden="true" />
        <div className="orbit-ring orbit-ring--inner" aria-hidden="true" />
        <picture>
          <source srcSet={logoWebp} type="image/webp" />
          <img
            className="hero-visual__logo"
            src={logoPng}
            alt={
              nightMode
                ? "Logo resmi HILALONE tema Night Vision Red"
                : "Logo resmi HILALONE tema Standard Dark"
            }
            width={204}
            height={204}
          />
        </picture>
      </div>

      <div className="hero-visual__layers">
        <div className="mini-layer-chip">
          <div className="mini-layer-chip__k">DATA MASTER</div>
          <div className="mini-layer-chip__v">float32 Linear</div>
        </div>
        <div className="mini-layer-chip">
          <div className="mini-layer-chip__k">CALIBRATION</div>
          <div className="mini-layer-chip__v">Master Flat Opt.</div>
        </div>
        <div className="mini-layer-chip">
          <div className="mini-layer-chip__k">DISPLAY</div>
          <div className="mini-layer-chip__v">MTF · Asinh · GHS</div>
        </div>
      </div>

      <div className="hero-visual__preview-strip">
        <img
          src={previewShot}
          alt={
            nightMode
              ? "Cuplikan antarmuka HILALONE dalam tema Night Vision Red memakai data sintetis"
              : "Cuplikan antarmuka HILALONE dalam tema Standard Dark memakai data sintetis"
          }
          width={800}
          height={450}
          loading="eager"
        />
        <div className="hero-visual__preview-caption">
          <span>Antarmuka Aktual Desktop Qt / PySide6</span>
          <span>Data uji sintetis (bukan observasi nyata)</span>
        </div>
      </div>
    </div>
  );
}
