import { AlertTriangle, BookOpenCheck } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { ABOUT_PILLARS } from "../data/hilaloneData";

export function AboutSection() {
  return (
    <section id="tentang" className="section section--alt">
      <div className="container about-layout">
        <div>
          <SectionHeader
            eyebrow="Tentang HILALONE"
            title="Alur Olah Citra Rukyat yang Transparan dan Dapat Diulang"
            subtitle="Dirancang untuk menjembatani perangkat lunak astronomi umum dengan kebutuhan praktis pengamatan hilal serta pembelajaran ilmu falak."
            icon={<BookOpenCheck size={14} aria-hidden="true" />}
          />

          <p className="card__text" style={{ fontSize: "0.98rem", marginBottom: "0.9rem" }}>
            Pengamatan bulan sabit muda sering berhadapan dengan langit senja yang
            sangat terang, gradien pencahayaan tajam, serta kontras sabit yang tipis.
            Pengeditan foto biasa berisiko memampatkan data ke 8-bit terlalu dini atau
            mengaburkan riwayat parameter pemrosesan.
          </p>

          <p className="card__text" style={{ fontSize: "0.98rem" }}>
            HILALONE hadir dengan pipeline berbasis Python &amp; PySide6 yang memproses
            nilai piksel secara linear dalam presisi <code>float32</code>, menjaga kanal
            asli citra, serta memisahkan master ilmiah dari pratinjau tampilan layar.
          </p>

          <div className="callout-box">
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6rem" }}>
              <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
              <div>
                <strong>Batasan Jujur MVP 1.0:</strong> HILALONE v1.0.0 merupakan
                aplikasi pengolahan citra astronomi. Versi ini <strong>belum</strong>{" "}
                memiliki fitur deteksi hilal otomatis, analisis kuantitatif visibilitas,
                maupun penentuan keberhasilan rukyat.
              </div>
            </div>
          </div>
        </div>

        <div className="grid-2">
          {ABOUT_PILLARS.map((pillar) => (
            <article key={pillar.title} className="card">
              <h3 className="card__title">{pillar.title}</h3>
              <p className="card__text">{pillar.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
