import { Milestone } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { ROADMAP_STAGES } from "../data/hilaloneData";

export function RoadmapSection() {
  return (
    <section id="roadmap" className="section">
      <div className="container">
        {/* Blok 7 Referensi: Services 01 (Kartu Kontras Gelap Aktif) | 02 | 03 */}
        <div className="surface-panel">
          <SectionHeader
            eyebrow="Peta Jalan Pengembangan"
            title="Roadmap Resmi Tiga Tahap HILALONE"
            subtitle="Tahap MVP 2.0 dan MVP 3.0 masih berstatus direncanakan (planned) tanpa jadwal rilis tetap agar pengujian keandalan MVP 1.0 tetap terjaga."
            centered
            icon={<Milestone size={14} aria-hidden="true" />}
          />

          <div className="grid-3 grid-3--subgrid roadmap-grid">
            {ROADMAP_STAGES.map((stage, idx) => {
              const isActive = stage.statusKind === "active";
              const stageNum = String(idx + 1).padStart(2, "0");

              return (
                <article
                  key={stage.id}
                  className={`card roadmap-card${
                    isActive ? " roadmap-card--focal" : " roadmap-card--quiet"
                  }`}
                >
                  <div className="roadmap-card__top">
                    <div>
                      <div className="eyebrow" style={{ marginBottom: "0.35rem" }}>
                        {stage.stage}
                      </div>
                      <span
                        className={`status-badge ${
                          isActive ? "status-badge--ok" : "status-badge--planned"
                        }`}
                      >
                        {stage.statusLabel}
                      </span>
                    </div>
                    <span className="roadmap-card__num" aria-hidden="true">
                      {stageNum}
                    </span>
                  </div>

                  <div className="roadmap-card__body">
                    <h3 className="card__title roadmap-card__title">{stage.title}</h3>
                    <p className="card__text">{stage.summary}</p>
                  </div>

                  <ul className="roadmap-list">
                    {stage.items.map((item) => (
                      <li key={item.label} className="roadmap-list__item">
                        <span>{item.label}</span>
                        <span className="roadmap-list__badge">{item.badge}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
