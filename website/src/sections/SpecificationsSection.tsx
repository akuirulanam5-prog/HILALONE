import { useState } from "react";
import { ChevronLeft, ChevronRight, Cpu, LayoutGrid, Table2 } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { TECH_SPECS } from "../data/hilaloneData";

const SPECS_PER_PAGE = 4;

export function SpecificationsSection() {
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const [pageIdx, setPageIdx] = useState(0);
  const [expandedCat, setExpandedCat] = useState<string | null>(null);

  const totalPages = Math.ceil(TECH_SPECS.length / SPECS_PER_PAGE);
  const safePage = Math.min(pageIdx, totalPages - 1);
  const visibleSpecs = TECH_SPECS.slice(
    safePage * SPECS_PER_PAGE,
    (safePage + 1) * SPECS_PER_PAGE
  );

  return (
    <section id="spesifikasi" className="section">
      <div className="container">
        {/* Blok 6 Referensi: Strip 4-Kolom + Navigasi Carousel & Mode Tabel Semantik */}
        <div className="surface-panel">
          <div className="specs-header-bar">
            <SectionHeader
              eyebrow="Spesifikasi Teknis"
              title="Arsitektur, Format &amp; Status Pengujian Aktual"
              subtitle="Menampilkan pustaka inti dan kondisi pengujian sebenarnya, membedakan lingkungan Windows yang telah diuji dengan yang belum diuji."
              icon={<Cpu size={14} aria-hidden="true" />}
            />

            <div className="pager-controls">
              {viewMode === "cards" ? (
                <div className="pager-nav" aria-label="Navigasi kartu spesifikasi">
                  <button
                    type="button"
                    className="pager-btn"
                    onClick={() => setPageIdx((p) => (p - 1 + totalPages) % totalPages)}
                    aria-label="Spesifikasi sebelumnya"
                  >
                    <ChevronLeft size={16} aria-hidden="true" />
                  </button>
                  <span className="pager-status">
                    {safePage + 1} / {totalPages}
                  </span>
                  <button
                    type="button"
                    className="pager-btn pager-btn--solid"
                    onClick={() => setPageIdx((p) => (p + 1) % totalPages)}
                    aria-label="Spesifikasi berikutnya"
                  >
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                </div>
              ) : null}

              <button
                type="button"
                className="btn btn--secondary btn--sm"
                aria-pressed={viewMode === "table"}
                onClick={() => setViewMode((m) => (m === "cards" ? "table" : "cards"))}
              >
                {viewMode === "cards" ? (
                  <>
                    <Table2 size={15} aria-hidden="true" />
                    <span>Tabel Lengkap ({TECH_SPECS.length})</span>
                  </>
                ) : (
                  <>
                    <LayoutGrid size={15} aria-hidden="true" />
                    <span>Ringkas 4 Kolom</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {viewMode === "cards" ? (
            <div className="grid-4 grid-4--subgrid">
              {visibleSpecs.map((row) => {
                const isPartial =
                  row.verificationTag.includes("Belum Diuji") ||
                  row.verificationTag.includes("Parsial");
                const isExpanded = expandedCat === row.category;

                return (
                  <article key={row.category} className="card spec-card">
                    <div className="spec-card__banner">
                      <span className="spec-row__cat">{row.category}</span>
                    </div>

                    <div className="spec-card__body">
                      <h3 className="card__title">{row.parameter}</h3>
                      <p className={`card__text${isExpanded ? "" : " spec-card__clamp"}`}>
                        {row.detail}
                      </p>
                    </div>

                    <div className="spec-card__foot">
                      <span
                        className={`status-badge ${
                          isPartial ? "status-badge--partial" : "status-badge--ok"
                        }`}
                      >
                        {row.verificationTag}
                      </span>
                      <button
                        type="button"
                        className="spec-card__toggle"
                        aria-expanded={isExpanded}
                        onClick={() =>
                          setExpandedCat(isExpanded ? null : row.category)
                        }
                      >
                        {isExpanded ? "Ringkas" : "Detail"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div
              className="specs-table-scroll"
              role="region"
              aria-label="Tabel spesifikasi teknis HILALONE"
              tabIndex={0}
            >
              <table className="specs-table">
                <caption className="visually-hidden">
                  Daftar spesifikasi teknis dan status verifikasi HILALONE
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Kategori</th>
                    <th scope="col">Parameter</th>
                    <th scope="col">Rincian Teknis</th>
                    <th scope="col">Status Uji</th>
                  </tr>
                </thead>
                <tbody>
                  {TECH_SPECS.map((row) => {
                    const isPartial =
                      row.verificationTag.includes("Belum Diuji") ||
                      row.verificationTag.includes("Parsial");
                    return (
                      <tr key={row.category}>
                        <th scope="row" className="spec-row__cat">
                          {row.category}
                        </th>
                        <td className="spec-row__param">{row.parameter}</td>
                        <td className="spec-row__detail">{row.detail}</td>
                        <td>
                          <span
                            className={`status-badge ${
                              isPartial ? "status-badge--partial" : "status-badge--ok"
                            }`}
                          >
                            {row.verificationTag}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
