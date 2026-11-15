import { Cpu } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { TECH_SPECS } from "../data/hilaloneData";

export function SpecificationsSection() {
  return (
    <section id="spesifikasi" className="section section--alt">
      <div className="container">
        <SectionHeader
          eyebrow="Spesifikasi Teknis"
          title="Arsitektur, Format &amp; Status Pengujian Aktual"
          subtitle="Menampilkan pustaka inti dan kondisi pengujian sebenarnya, membedakan lingkungan Windows yang telah diuji dengan yang belum diuji."
          icon={<Cpu size={14} aria-hidden="true" />}
        />

        <div className="specs-table-wrap" role="region" aria-label="Tabel spesifikasi teknis HILALONE">
          {TECH_SPECS.map((row) => (
            <div key={row.category} className="spec-row">
              <div className="spec-row__cat">{row.category}</div>
              <div className="spec-row__param">{row.parameter}</div>
              <div className="spec-row__detail">{row.detail}</div>
              <div>
                <span
                  className={`status-badge ${
                    row.verificationTag.includes("Belum Diuji") || row.verificationTag.includes("Parsial")
                      ? "status-badge--partial"
                      : "status-badge--ok"
                  }`}
                >
                  {row.verificationTag}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
