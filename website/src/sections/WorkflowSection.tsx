import { useState } from "react";
import { GitCommitHorizontal } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { WORKFLOW_STEPS } from "../data/hilaloneData";

export function WorkflowSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const current = WORKFLOW_STEPS[activeIndex];

  return (
    <section id="alur-kerja" className="section">
      <div className="container">
        <SectionHeader
          eyebrow="Arsitektur Pipeline"
          title="Alur Kerja Pemrosesan Aktual HILALONE"
          subtitle="Setiap tahapan mengikuti urutan eksekusi aktual pada ProcessingPipelineOrchestrator. Klik tiap tahap untuk meninjau peran dan keluarannya."
          icon={<GitCommitHorizontal size={14} aria-hidden="true" />}
        />

        <div className="workflow-legend">
          <span className="status-badge status-badge--ok">Tahap Wajib Pipeline</span>
          <span className="status-badge status-badge--planned">Khusus Multi-Frame / Video / SER</span>
          <span className="status-badge status-badge--partial">Garis Putus-Putus: Opsional (Flat Calibration)</span>
        </div>

        <div className="workflow-grid">
          {WORKFLOW_STEPS.map((step, idx) => {
            const isOptional = step.modeTag === "Opsional";
            const isActive = idx === activeIndex;
            const badgeClass =
              step.modeTag === "Wajib"
                ? "status-badge--ok"
                : step.modeTag === "Opsional"
                  ? "status-badge--partial"
                  : "status-badge--planned";

            return (
              <button
                key={step.code}
                type="button"
                className={`workflow-step${isOptional ? " workflow-step--optional" : ""}${
                  isActive ? " is-active" : ""
                }`}
                aria-pressed={isActive}
                onClick={() => setActiveIndex(idx)}
              >
                <div className="workflow-step__head">
                  <span className="workflow-step__num">
                    {step.stepNumber} · {step.code}
                  </span>
                  <span className={`status-badge ${badgeClass}`}>{step.modeTag}</span>
                </div>
                <div style={{ fontWeight: 700, fontSize: "0.96rem", marginBottom: "0.3rem" }}>
                  {step.title}
                </div>
                <div className="card__text" style={{ fontSize: "0.84rem" }}>
                  {step.summary}
                </div>
              </button>
            );
          })}
        </div>

        <div className="workflow-detail-card" aria-live="polite">
          <div className="eyebrow" style={{ marginBottom: "0.35rem" }}>
            Tahap {current.stepNumber} — {current.code} ({current.modeTag})
          </div>
          <h3 style={{ margin: "0 0 0.5rem 0", fontSize: "1.18rem" }}>{current.title}</h3>
          <p className="card__text" style={{ marginBottom: "0.85rem", fontSize: "0.96rem" }}>
            {current.technicalDetail}
          </p>
          <div className="workflow-detail-card__output">
            Keluaran tahap: {current.outputs}
          </div>
        </div>
      </div>
    </section>
  );
}
