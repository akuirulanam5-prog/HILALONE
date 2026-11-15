import { Check, ShieldCheck } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { INTEGRITY_LAYERS, NON_INVENTION_RULES } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

export function ScientificIntegritySection() {
  return (
    <section id="integritas" className="section section--alt">
      <div className="container">
        <SectionHeader
          eyebrow="Scientific Integrity"
          title={`"${siteConfig.philosophy}"`}
          subtitle="Setiap cabang data dipisahkan secara eksplisit di dalam PipelineResult sehingga pengamat dapat mengekspor data ilmiah linear murni tanpa bercampur kurva tampilan."
          icon={<ShieldCheck size={14} aria-hidden="true" />}
        />

        <div className="integrity-grid" style={{ marginBottom: "1.75rem" }}>
          {INTEGRITY_LAYERS.map((layer) => (
            <article key={layer.code} className="layer-card">
              <div className="layer-card__code">CABANG {layer.code}</div>
              <h3 className="card__title" style={{ fontSize: "0.98rem", marginBottom: 0 }}>
                {layer.title}
              </h3>
              <div className="layer-card__dtype">{layer.dtype}</div>
              <p className="card__text" style={{ fontSize: "0.85rem" }}>
                {layer.role}
              </p>
              <div
                style={{
                  marginTop: "auto",
                  paddingTop: "0.55rem",
                  borderTop: "1px solid var(--border-subtle)",
                  fontSize: "0.8rem",
                  color: "#cbd5e1",
                }}
              >
                {layer.guarantee}
              </div>
            </article>
          ))}
        </div>

        <div className="card">
          <h3 className="card__title" style={{ marginBottom: "0.85rem" }}>
            Jaminan Transparansi &amp; Larangan Pemrosesan MVP 1.0
          </h3>
          <ul className="rules-list">
            {NON_INVENTION_RULES.map((rule) => (
              <li key={rule}>
                <Check
                  size={17}
                  style={{ color: "var(--accent-emerald)", flexShrink: 0, marginTop: 3 }}
                  aria-hidden="true"
                />
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
