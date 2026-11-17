import { useState } from "react";
import { ChevronLeft, ChevronRight, Expand, Monitor } from "lucide-react";
import { ScreenshotLightbox } from "../components/ScreenshotLightbox";
import { SectionHeader } from "../components/SectionHeader";
import { SCREENSHOTS } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

export function PreviewGallerySection() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);

  const active = SCREENSHOTS[selectedIdx];
  const peekIdx = (selectedIdx + 1) % SCREENSHOTS.length;
  const peek = SCREENSHOTS[peekIdx];

  return (
    <section id="antarmuka" className="section">
      <div className="container">
        {/* Blok 4 Referensi: Spotlight Showcase — Layered Preview Deck kiri | Detail Card + CTA kanan */}
        <div className="surface-panel">
          <SectionHeader
            eyebrow="Pratinjau Antarmuka Nyata"
            title={`Galeri Antarmuka Desktop HILALONE v${siteConfig.version}`}
            subtitle="Seluruh tangkapan layar diambil langsung dari aplikasi PySide6 HILALONE. Citra pemrosesan menggunakan data uji sintetis, bukan hasil observasi nyata."
            centered
            icon={<Monitor size={14} aria-hidden="true" />}
          />

          <div className="gallery-spotlight">
            <div className="gallery-deck">
              {/* Lapisan belakang memberi konteks tangkapan layar berikutnya (mengikuti deck berlapis referensi) */}
              <div className="gallery-deck__back" aria-hidden="true">
                <img
                  src={peek.src800}
                  alt=""
                  width={800}
                  height={450}
                  loading="lazy"
                />
              </div>

              <button
                type="button"
                className="gallery-deck__front"
                onClick={() => setLightboxIdx(selectedIdx)}
                aria-label={`Perbesar screenshot: ${active.title}`}
              >
                <img
                  className="gallery-stage__img"
                  src={active.src1600}
                  alt={active.alt}
                  width={1600}
                  height={900}
                />
                <span className="gallery-stage__zoom-btn" aria-hidden="true">
                  <Expand size={15} />
                  <span>Perbesar Tampilan</span>
                </span>
              </button>
            </div>

            <div className="gallery-spotlight__side">
              <div className="gallery-detail-card">
                <div className="gallery-detail-card__top">
                  <span className="eyebrow" style={{ marginBottom: 0 }}>
                    {active.category}
                    {active.isSyntheticSample ? " · Data Uji Sintetis" : ""}
                  </span>
                  <span className="pager-status">
                    {String(selectedIdx + 1).padStart(2, "0")} /{" "}
                    {String(SCREENSHOTS.length).padStart(2, "0")}
                  </span>
                </div>

                <h3 className="gallery-detail-card__title">{active.title}</h3>
                <p className="card__text">{active.caption}</p>

                <div className="gallery-detail-card__pager">
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    onClick={() =>
                      setSelectedIdx((selectedIdx - 1 + SCREENSHOTS.length) % SCREENSHOTS.length)
                    }
                    aria-label="Screenshot sebelumnya"
                  >
                    <ChevronLeft size={16} aria-hidden="true" />
                    <span>Sebelumnya</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    onClick={() => setSelectedIdx((selectedIdx + 1) % SCREENSHOTS.length)}
                    aria-label="Screenshot berikutnya"
                  >
                    <span>Berikutnya</span>
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                </div>
              </div>

              <button
                type="button"
                className="btn btn--primary gallery-spotlight__cta"
                onClick={() => setLightboxIdx(selectedIdx)}
              >
                <Expand size={17} aria-hidden="true" />
                <span>Buka Pratinjau Modal Penuh</span>
              </button>
            </div>
          </div>

          <div className="thumb-grid" role="list" aria-label="Daftar screenshot antarmuka">
            {SCREENSHOTS.map((shot, idx) => {
              const isActive = idx === selectedIdx;
              return (
                <button
                  key={shot.id}
                  type="button"
                  className={`thumb-btn${isActive ? " is-active" : ""}`}
                  aria-pressed={isActive}
                  onClick={() => setSelectedIdx(idx)}
                >
                  <img
                    src={shot.src800}
                    alt={shot.title}
                    width={800}
                    height={450}
                    loading="lazy"
                  />
                  <span className="thumb-btn__label">{shot.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <ScreenshotLightbox
        items={SCREENSHOTS}
        activeIndex={lightboxIdx}
        onClose={() => setLightboxIdx(null)}
        onChangeIndex={(next) => {
          setLightboxIdx(next);
          setSelectedIdx(next);
        }}
      />
    </section>
  );
}
