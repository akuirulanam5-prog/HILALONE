import { useRef, useState, type KeyboardEvent } from "react";
import {
  Activity,
  BarChart3,
  Camera,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
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

const CORE_FEATURE_IDS = new Set([
  "multi-format-input",
  "image-stacking",
  "profiles",
  "background-extraction",
  "luminance-enhancement",
  "image-enhancement",
  "scientific-export",
]);

const PAGE_SIZE = 6;

function tabIdFor(category: FeatureCategory): string {
  return `feature-tab-${category.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function FeaturesSection() {
  const [selectedCategory, setSelectedCategory] = useState<FeatureCategory>("Semua");
  const [pageIndex, setPageIndex] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const filteredFeatures =
    selectedCategory === "Semua"
      ? FEATURES
      : FEATURES.filter((item) => item.category === selectedCategory);

  const canPaginate = selectedCategory === "Semua" && !showAll;
  const totalPages = canPaginate ? Math.ceil(filteredFeatures.length / PAGE_SIZE) : 1;
  const safePageIndex = Math.min(pageIndex, totalPages - 1);
  const visibleFeatures = canPaginate
    ? filteredFeatures.slice(safePageIndex * PAGE_SIZE, (safePageIndex + 1) * PAGE_SIZE)
    : filteredFeatures;

  const selectCategory = (category: FeatureCategory, index: number) => {
    setSelectedCategory(category);
    setPageIndex(0);
    setShowAll(false);
    tabRefs.current[index]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentIdx: number) => {
    let nextIdx: number | null = null;
    if (event.key === "ArrowRight") {
      nextIdx = (currentIdx + 1) % FEATURE_CATEGORIES.length;
    } else if (event.key === "ArrowLeft") {
      nextIdx = (currentIdx - 1 + FEATURE_CATEGORIES.length) % FEATURE_CATEGORIES.length;
    } else if (event.key === "Home") {
      nextIdx = 0;
    } else if (event.key === "End") {
      nextIdx = FEATURE_CATEGORIES.length - 1;
    }
    if (nextIdx !== null) {
      event.preventDefault();
      const targetTab = tabRefs.current[nextIdx];
      targetTab?.focus();
      selectCategory(FEATURE_CATEGORIES[nextIdx], nextIdx);
    }
  };

  return (
    <section id="fitur" className="section section--light">
      <div className="container">
        <div className="section-panel">
          <div className="section-head-row">
            <SectionHeader
              eyebrow="Fitur Utama (Audit MVP 1.0)"
              title="20 Kemampuan Terimplementasi untuk Olah Citra Ilmiah"
              subtitle="Kemampuan inti pemrosesan disorot sebagai fitur prioritas; seluruh daftar diaudit langsung dari kode sumber HILALONE."
              icon={<Layers size={14} aria-hidden="true" />}
            />

            <div className="filter-bar__badges">
              <span className="status-badge status-badge--ok">TERUJI: 19 Fitur</span>
              <span className="status-badge status-badge--partial">PARSIAL: 1 Fitur (RAW Kamera)</span>
            </div>
          </div>

          <div className="filter-bar">
            <div className="tabs-scroller">
              <div className="filter-tabs" role="tablist" aria-label="Filter kategori fitur">
                {FEATURE_CATEGORIES.map((category, idx) => {
                  const active = category === selectedCategory;
                  return (
                    <button
                      key={category}
                      ref={(el) => {
                        tabRefs.current[idx] = el;
                      }}
                      id={tabIdFor(category)}
                      type="button"
                      role="tab"
                      tabIndex={active ? 0 : -1}
                      aria-selected={active}
                      className="filter-tab"
                      onClick={() => selectCategory(category, idx)}
                      onKeyDown={(e) => handleTabKeyDown(e, idx)}
                    >
                      {category}
                    </button>
                  );
                })}
              </div>
            </div>

            {selectedCategory === "Semua" ? (
              <div className="pager-controls">
                {!showAll ? (
                  <div className="pager-nav" aria-label="Navigasi halaman fitur">
                    <button
                      type="button"
                      className="pager-btn"
                      onClick={() => setPageIndex((p) => (p - 1 + totalPages) % totalPages)}
                      aria-label="Halaman fitur sebelumnya"
                    >
                      <ChevronLeft size={17} aria-hidden="true" />
                    </button>
                    <span className="pager-status">
                      {safePageIndex + 1} / {totalPages}
                    </span>
                    <button
                      type="button"
                      className="pager-btn pager-btn--solid"
                      onClick={() => setPageIndex((p) => (p + 1) % totalPages)}
                      aria-label="Halaman fitur berikutnya"
                    >
                      <ChevronRight size={17} aria-hidden="true" />
                    </button>
                  </div>
                ) : null}

                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  aria-pressed={showAll}
                  onClick={() => setShowAll((prev) => !prev)}
                >
                  {showAll ? "Tampilkan Ringkas (6)" : `Lihat Semua (${filteredFeatures.length})`}
                </button>
              </div>
            ) : null}
          </div>

          <div role="tabpanel" aria-labelledby={tabIdFor(selectedCategory)} tabIndex={0}>
            <div className="grid-3 grid-3--subgrid">
              {visibleFeatures.map((feature) => {
                const IconComp = ICON_MAP[feature.iconName];
                const isCore = CORE_FEATURE_IDS.has(feature.id);

                return (
                  <article
                    key={feature.id}
                    className={`card feature-card${isCore ? " feature-card--core" : ""}`}
                  >
                    <div className="feature-card__header">
                      <span className="feature-card__cat">
                        <IconComp size={16} className="feature-card__icon-inline" aria-hidden="true" />
                        <span>{feature.category}</span>
                      </span>
                      <div className="feature-card__tags">
                        {isCore ? <span className="feature-card__core-tag">INTI</span> : null}
                        <span
                          className={`status-badge ${
                            feature.status === "TERUJI" ? "status-badge--ok" : "status-badge--partial"
                          }`}
                        >
                          {feature.status === "TERUJI" ? (
                            <CheckCircle2 size={12} aria-hidden="true" />
                          ) : null}
                          {feature.status}
                        </span>
                      </div>
                    </div>

                    <div className="feature-card__body">
                      <h3 className="card__title">{feature.name}</h3>
                      <p className="card__text">{feature.description}</p>
                    </div>

                    <div className="feature-card__benefit">
                      <div>
                        <strong>Manfaat:</strong> {feature.benefit}
                      </div>
                      {feature.statusNote ? (
                        <div className="feature-card__note">Catatan uji: {feature.statusNote}</div>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          {canPaginate ? (
            <div className="pager-dots" aria-label="Indikator halaman fitur">
              {Array.from({ length: totalPages }, (_, idx) => (
                <button
                  key={idx}
                  type="button"
                  className={`pager-dot${idx === safePageIndex ? " is-active" : ""}`}
                  aria-label={`Halaman fitur ${idx + 1}`}
                  aria-current={idx === safePageIndex ? "step" : undefined}
                  onClick={() => setPageIndex(idx)}
                />
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
