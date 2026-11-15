import { useState } from "react";
import {
  Activity,
  BarChart3,
  Camera,
  CheckCircle2,
  Contrast,
  FileCode2,
  FileOutput,
  Files,
  Film,
  FolderOpen,
  Gauge,
  Image,
  Images,
  Info,
  Layers,
  ListChecks,
  Moon,
  ScanLine,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import {
  FEATURE_CATEGORIES,
  FEATURES,
  type FeatureCategory,
  type FeatureItem,
} from "../data/hilaloneData";

const ICON_MAP: Record<FeatureItem["iconName"], LucideIcon> = {
  Files,
  FileCode2,
  Image,
  Camera,
  Film,
  Images,
  FolderOpen,
  ListChecks,
  Info,
  Sparkles,
  SlidersHorizontal,
  Layers,
  Gauge,
  ScanLine,
  Contrast,
  BarChart3,
  Activity,
  Terminal,
  FileOutput,
  Moon,
};

export function FeaturesSection() {
  const [selectedCategory, setSelectedCategory] = useState<FeatureCategory>("Semua");

  const visibleFeatures =
    selectedCategory === "Semua"
      ? FEATURES
      : FEATURES.filter((item) => item.category === selectedCategory);

  return (
    <section id="fitur" className="section">
      <div className="container">
        <SectionHeader
          eyebrow="Fitur Utama (Audit MVP 1.0)"
          title="20 Kemampuan Terimplementasi untuk Olah Citra Ilmiah"
          subtitle="Seluruh daftar di bawah diaudit langsung dari kode sumber HILALONE v1.0.0 dan dipisahkan status pengujiannya secara terbuka."
          icon={<Layers size={14} aria-hidden="true" />}
        />

        <div className="filter-bar">
          <div className="filter-tabs" role="tablist" aria-label="Filter kategori fitur">
            {FEATURE_CATEGORIES.map((category) => {
              const active = category === selectedCategory;
              return (
                <button
                  key={category}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`filter-tab${active ? " is-active" : ""}`}
                  onClick={() => setSelectedCategory(category)}
                >
                  {category}
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <span className="status-badge status-badge--ok">TERUJI: 19 Fitur</span>
            <span className="status-badge status-badge--partial">PARSIAL: 1 Fitur (RAW Kamera Asli)</span>
          </div>
        </div>

        <div className="grid-3">
          {visibleFeatures.map((feature) => {
            const IconComp = ICON_MAP[feature.iconName];
            return (
              <article key={feature.id} className="card feature-card">
                <div className="feature-card__top">
                  <div className="feature-card__icon">
                    <IconComp size={19} aria-hidden="true" />
                  </div>
                  <span
                    className={`status-badge ${
                      feature.status === "TERUJI" ? "status-badge--ok" : "status-badge--partial"
                    }`}
                  >
                    {feature.status === "TERUJI" ? (
                      <CheckCircle2 size={11} aria-hidden="true" />
                    ) : null}
                    {feature.status}
                  </span>
                </div>

                <div>
                  <h3 className="card__title">{feature.name}</h3>
                  <p className="card__text">{feature.description}</p>
                </div>

                <div className="feature-card__benefit">
                  <strong>Manfaat:</strong> {feature.benefit}
                  {feature.statusNote ? (
                    <div style={{ marginTop: "0.35rem", color: "#f3d08a", fontSize: "0.78rem" }}>
                      Catatan uji: {feature.statusNote}
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
