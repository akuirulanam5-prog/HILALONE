import { AlertTriangle, BookOpenCheck } from "lucide-react";
import { ABOUT_PILLARS } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

const PROOF_METRICS = [
  {
    value: "float32",
    label: "Presisi internal linear penuh sebelum ekspor visual PNG 8-bit.",
  },
  {
    value: "251 Lulus",
    label: "Unit test terverifikasi memakai data sintetis (3 skipped krn sampel eksternal).",
  },
  {
    value: "5 Cabang",
    label: "Pemisahan cabang data A–F antara master linear dan display preview.",
  },
] as const;

export function AboutSection() {
  return (
    <section id="tentang" className="section">
      <div className="container">
        {/* Blok 5 Referensi: Asimetris 3 Kolom — Metrik Kiri | Visual Fokus Tengah | Narasi Editorial Kanan */}
        <div className="surface-panel">
          <div className="about-asymmetric">
            <dl className="about-metrics" aria-label="Fakta teknis utama HILALONE">
              {PROOF_METRICS.map((metric) => (
                <div key={metric.value} className="about-metric-item">
                  <dt className="about-metric-item__val">{metric.value}</dt>
                  <dd className="about-metric-item__desc">{metric.label}</dd>
                </div>
              ))}
            </dl>

            <figure className="about-focal">
              <img
                src="/screenshots/processing-result-dark-800.webp"
                alt="Hasil pemrosesan otomatis profil Basic standar pada 8 frame sintetis di HILALONE"
                width={800}
                height={450}
                loading="lazy"
              />
              <figcaption className="about-focal__caption">
                Keluaran cabang tampilan vs master linear pada data uji sintetis.
              </figcaption>
            </figure>

            <div className="about-narrative">
              <div className="eyebrow">
                <BookOpenCheck size={14} aria-hidden="true" />
                <span>Tentang HILALONE</span>
              </div>
              <h2 className="section-title" style={{ fontSize: "clamp(1.35rem, 2.2vw, 1.9rem)" }}>
                Alur Olah Citra Rukyat yang Transparan dan Dapat Diulang
              </h2>
              <p className="card__text" style={{ marginBottom: "0.75rem" }}>
                Pengamatan bulan sabit muda berhadapan dengan langit senja yang terang, gradien
                pencahayaan tajam, serta kontras sabit tipis. Pengeditan foto umum berisiko
                memampatkan data ke 8-bit terlalu dini atau menghilangkan riwayat parameter.
              </p>
              <p className="card__text">
                HILALONE memproses nilai piksel secara linear dalam presisi <code>float32</code>,
                menjaga kanal asli mono maupun RGB, dan memisahkan master ilmiah dari pratinjau
                layar.
              </p>

              <div className="notice-strip" role="note">
                <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
                <div>
                  <strong>Batasan Jujur MVP 1.0 (v{siteConfig.version}):</strong> HILALONE
                  merupakan perangkat lunak pengolahan citra astronomi dan <strong>belum</strong>{" "}
                  memiliki fitur deteksi hilal otomatis, analisis kuantitatif visibilitas, ataupun
                  penentuan keberhasilan rukyat.
                </div>
              </div>
            </div>
          </div>

          <div className="about-pillars-row">
            {ABOUT_PILLARS.map((pillar) => (
              <div key={pillar.title} className="about-pillar-item">
                <h3 className="card__title">{pillar.title}</h3>
                <p className="card__text">{pillar.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
