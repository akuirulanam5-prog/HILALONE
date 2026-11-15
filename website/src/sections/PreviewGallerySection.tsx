import { useState } from "react";
import { Expand, Monitor } from "lucide-react";
import { ScreenshotLightbox } from "../components/ScreenshotLightbox";
import { SectionHeader } from "../components/SectionHeader";
import { SCREENSHOTS } from "../data/hilaloneData";

export function PreviewGallerySection() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);

  const active = SCREENSHOTS[selectedIdx];

  return (
    <section id="antarmuka" className="section section--alt">
      <div className="container">
        <SectionHeader
          eyebrow="Pratinjau Antarmuka Nyata"
          title="Galeri Antarmuka Desktop HILALONE v1.0.0"
          subtitle="Seluruh tangkapan layar diambil langsung dari aplikasi PySide6 HILALONE. Tampilan pemrosesan di viewer memakai data uji sintetis, bukan hasil observasi nyata."
          icon={<Monitor size={14} aria-hidden="true" />}
        />

        <div className="gallery-stage">
          <div
            className="gallery-stage__viewport"
            onClick={() => setLightboxIdx(selectedIdx)}
            role="button"
            tabIndex={0}
            aria-label={`Perbesar screenshot: ${active.title}`}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setLightboxIdx(selectedIdx);
              }
            }}
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
          </div>

          <div className="gallery-stage__meta">
            <div>
              <div className="eyebrow" style={{ marginBottom: "0.25rem" }}>
                {active.category}
                {active.isSyntheticSample ? " · Data Uji Sintetis" : ""}
              </div>
              <h3 style={{ margin: "0 0 0.35rem 0", fontSize: "1.12rem" }}>{active.title}</h3>
              <p className="card__text" style={{ maxWidth: "72ch" }}>
                {active.caption}
              </p>
            </div>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setLightboxIdx(selectedIdx)}
            >
              <Expand size={16} aria-hidden="true" />
              <span>Buka Modal</span>
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
