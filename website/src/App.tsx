import { Navbar } from "./components/Navbar";
import { AboutSection } from "./sections/AboutSection";
import { DownloadSection } from "./sections/DownloadSection";
import { FaqSection } from "./sections/FaqSection";
import { FeaturesSection } from "./sections/FeaturesSection";
import { Footer } from "./sections/Footer";
import { HeroSection } from "./sections/HeroSection";
import { PreviewGallerySection } from "./sections/PreviewGallerySection";
import { RoadmapSection } from "./sections/RoadmapSection";
import { ScientificIntegritySection } from "./sections/ScientificIntegritySection";
import { SpecificationsSection } from "./sections/SpecificationsSection";
import { WorkflowSection } from "./sections/WorkflowSection";

export function App() {
  return (
    <div className="app-shell">
      <a className="skip-link visually-hidden" href="#konten-judul">
        Langsung ke konten utama
      </a>
      <Navbar />
      <main id="konten-utama">
        {/* Blok 1: Framed Split Hero + 3-Pillar Proof Strip */}
        <HeroSection />
        {/* Blok 2: Filterable Capabilities Grid + Paginasi */}
        <FeaturesSection />
        {/* Blok 3: Editorial 50/50 Split Guide + Vertical Step Spine */}
        <WorkflowSection />
        {/* Blok 4: Asymmetric Layered Visual Gallery + Native Dialog Lightbox */}
        <PreviewGallerySection />
        {/* Blok 5: Asymmetric 3-Column Metrics + Visual Focal + Narrative + Cabang A-F */}
        <AboutSection />
        <ScientificIntegritySection />
        {/* Blok 6: 4-Column Bento Technical Specs / Semantic Table */}
        <SpecificationsSection />
        {/* Blok 7: Contrasting Focal Card 01 + Quiet Cards 02-03 */}
        <RoadmapSection />
        {/* Blok 8: Distribusi Installer + Native Details FAQ */}
        <DownloadSection />
        <FaqSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
