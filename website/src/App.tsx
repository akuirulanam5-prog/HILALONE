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
      <a className="skip-link" href="#konten-utama">
        Langsung ke konten utama
      </a>
      <Navbar />
      <main id="konten-utama">
        <HeroSection />
        <AboutSection />
        <FeaturesSection />
        <PreviewGallerySection />
        <WorkflowSection />
        <ScientificIntegritySection />
        <RoadmapSection />
        <SpecificationsSection />
        <DownloadSection />
        <FaqSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
