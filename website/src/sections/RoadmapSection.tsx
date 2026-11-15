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
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "0.5rem",
                    marginBottom: "0.75rem",
                    flexWrap: "wrap",
                  }}
                >
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

                <ul
                  style={{
                    margin: 0,
                    padding: 0,
                    listStyle: "none",
                    display: "grid",
                    gap: "0.55rem",
                    borderTop: "1px solid var(--border-subtle)",
                    paddingTop: "0.85rem",
                  }}
                >
                  {stage.items.map((item) => (
                    <li
                      key={item.label}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "0.5rem",
                        fontSize: "0.84rem",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <span>{item.label}</span>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.72rem",
                          color: "var(--accent-cyan)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.badge}
                      </span>
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
