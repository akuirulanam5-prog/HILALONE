import { AlertTriangle, BookOpenCheck } from "lucide-react";
import { ABOUT_PILLARS } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

const PROOF_METRICS = [
  {
    value: "float32",
    label: "Presisi internal linear penuh hingga tahap ekspor FITS/TIFF ilmiah.",
  },
  {
    value: "251 Lulus",
    label: "Unit test offscreen Pytest memakai data sintetis (3 skipped krn sampel lokal tidak tersedia).",
  },
  {
    value: "A–F Terpisah",
    label: "Lima cabang data internal yang memisahkan master linear dari pratinjau visual.",
  },
] as const;

export function AboutSection() {
  return (
    <section id="tentang" className="section section--alt">
      <div className="container">
        <div className="about-layout">
          <div className="about-narrative">
            <div className="eyebrow">
              <BookOpenCheck size={14} aria-hidden="true" />
              <span>Tentang HILALONE</span>
            </div>
            <h2 className="section-title">
              Alur Olah Citra Rukyat yang Transparan dan Dapat Diulang
            </h2>
            <p className="about-lead">
              Pengamatan bulan sabit muda berhadapan dengan langit senja yang terang, gradien
              pencahayaan tajam, serta kontras sabit tipis. Pengeditan foto umum berisiko
              memampatkan data ke 8-bit terlalu dini atau menghilangkan riwayat parameter.
            </p>
            <p className="card__text">
              HILALONE memproses nilai piksel secara linear dalam presisi <code>float32</code>,
              menjaga kanal asli mono maupun RGB, dan memisahkan master ilmiah dari pratinjau
              layar.
            </p>

            <div className="notice-banner" role="note">
              <AlertTriangle size={18} className="notice-banner__icon" aria-hidden="true" />
              <div>
                <strong>Batasan Jujur MVP 1.0 (v{siteConfig.version}):</strong> HILALONE merupakan
                perangkat lunak pengolahan citra astronomi dan <strong>belum</strong> memiliki fitur
                deteksi hilal otomatis, analisis kuantitatif visibilitas, ataupun penentuan
                keberhasilan rukyat.
              </div>
            </div>
          </div>

          <div className="about-evidence">
            <dl className="about-metrics" aria-label="Fakta teknis terverifikasi HILALONE">
              {PROOF_METRICS.map((metric) => (
                <div key={metric.value} className="about-metric-item">
                  <dt className="about-metric-item__val">{metric.value}</dt>
                  <dd className="about-metric-item__desc">{metric.label}</dd>
                </div>
              ))}
            </dl>

            <dl className="about-pillars-grid">
              {ABOUT_PILLARS.map((pillar) => (
                <div key={pillar.title} className="about-pillar-item">
                  <dt className="card__title">{pillar.title}</dt>
                  <dd className="card__text">{pillar.description}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
