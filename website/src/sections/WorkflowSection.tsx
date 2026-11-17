import { useState } from "react";
import { GitCommitHorizontal } from "lucide-react";
import { WORKFLOW_STEPS } from "../data/hilaloneData";

export function WorkflowSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const current = WORKFLOW_STEPS[activeIndex];

  return (
    <section id="alur-kerja" className="section">
      <div className="container">
        {/* Blok 3 Referensi: Editorial 50/50 Split — Judul & Inspector kiri | Vertical Step Spine kanan */}
        <div className="surface-panel workflow-editorial">
          <div className="workflow-editorial__intro">
            <div className="eyebrow">
              <GitCommitHorizontal size={14} aria-hidden="true" />
              <span>Arsitektur Pipeline</span>
            </div>
            <h2 className="section-title">Alur Kerja Pemrosesan 9 Tahap</h2>
            <p className="section-subtitle">
              Setiap tahapan mengikuti urutan eksekusi aktual pada{" "}
              <code>ProcessingPipelineOrchestrator</code>. Pilih salah satu langkah untuk
              meninjau peran dan keluarannya.
            </p>

            <div className="workflow-legend">
              <span className="status-badge status-badge--ok">Wajib Pipeline</span>
              <span className="status-badge status-badge--planned">Multi-Frame / Video / SER</span>
              <span className="status-badge status-badge--partial">Opsional: Flat Calibration</span>
            </div>

            <div className="workflow-detail-card" aria-live="polite">
              <div className="eyebrow" style={{ marginBottom: "0.35rem" }}>
                Tahap {current.stepNumber} — {current.code} ({current.modeTag})
              </div>
              <h3 className="workflow-detail-card__title">{current.title}</h3>
              <p className="card__text" style={{ marginBottom: "0.85rem" }}>
                {current.technicalDetail}
              </p>
              <div className="workflow-detail-card__output">
                Keluaran tahap: {current.outputs}
              </div>
            </div>
          </div>

          <ol className="workflow-timeline" aria-label="Daftar langkah pipeline HILALONE">
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
                <li
                  key={step.code}
                  className={`workflow-timeline__item${
                    isOptional ? " is-optional" : ""
                  }${isActive ? " is-active" : ""}`}
                >
                  <button
                    type="button"
                    className="workflow-timeline__btn"
                    aria-pressed={isActive}
                    onClick={() => setActiveIndex(idx)}
                  >
                    <div className="workflow-step__head">
                      <span className="workflow-step__num">
                        Step {step.stepNumber} · {step.code}
                      </span>
                      <span className={`status-badge ${badgeClass}`}>{step.modeTag}</span>
                    </div>
                    <div className="workflow-timeline__title">{step.title}</div>
                    <p className="card__text">{step.summary}</p>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </section>
  );
}
