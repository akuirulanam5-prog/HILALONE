import { Check, ShieldCheck } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { INTEGRITY_LAYERS, NON_INVENTION_RULES } from "../data/hilaloneData";
import { siteConfig } from "../data/siteConfig";

export function ScientificIntegritySection() {
  return (
    <section id="integritas" className="section">
      <div className="container">
        <div className="surface-panel">
          <SectionHeader
            eyebrow="Scientific Integrity"
            title={`"${siteConfig.philosophy}"`}
            subtitle="Setiap cabang data dipisahkan eksplisit di dalam PipelineResult sehingga pengamat dapat mengekspor data ilmiah linear murni tanpa bercampur kurva tampilan."
            icon={<ShieldCheck size={14} aria-hidden="true" />}
          />

          <div className="integrity-grid">
            {INTEGRITY_LAYERS.map((layer) => (
              <article key={layer.code} className="layer-card">
                <div className="layer-card__top">
                  <div className="layer-card__code">CABANG {layer.code}</div>
                  <div className="layer-card__dtype">{layer.dtype}</div>
                </div>
                <h3 className="card__title">{layer.title}</h3>
                <p className="card__text">{layer.role}</p>
                <div className="layer-card__guarantee">{layer.guarantee}</div>
              </article>
            ))}
          </div>

          <div className="integrity-rules-band">
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
      </div>
    </section>
  );
}
