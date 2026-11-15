import { Milestone } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { ROADMAP_STAGES } from "../data/hilaloneData";

export function RoadmapSection() {
  return (
    <section id="roadmap" className="section">
      <div className="container">
        <SectionHeader
          eyebrow="Peta Jalan Pengembangan"
          title="Roadmap Resmi Tiga Tahap HILALONE"
          subtitle="Tahap MVP 2.0 dan MVP 3.0 masih berada dalam status direncanakan (planned) tanpa jadwal rilis tetap agar fokus pengujian MVP 1.0 tetap terjaga."
          icon={<Milestone size={14} aria-hidden="true" />}
        />

        <div className="grid-3">
          {ROADMAP_STAGES.map((stage) => {
            const isActive = stage.statusKind === "active";
            return (
              <article
                key={stage.id}
                className="card"
                style={isActive ? { borderColor: "var(--border-accent)" } : undefined}
              >
                <div className="roadmap-card__head">
                  <span className="eyebrow" style={{ marginBottom: 0 }}>
                    {stage.stage}
                  </span>
                  <span
                    className={`status-badge ${
                      isActive ? "status-badge--ok" : "status-badge--planned"
                    }`}
                  >
                    {stage.statusLabel}
                  </span>
                </div>

                <h3 className="card__title" style={{ fontSize: "1.1rem" }}>
                  {stage.title}
                </h3>
                <p className="card__text" style={{ marginBottom: "1rem" }}>
                  {stage.summary}
                </p>

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
    </section>
  );
}
