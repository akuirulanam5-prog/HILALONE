import { siteConfig } from "../data/siteConfig";

export function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__grid">
          <div>
            <div className="footer__brand">
              <picture>
                <source srcSet="/branding/hilalone-icon-standard-96.webp" type="image/webp" />
                <img
                  className="footer__logo"
                  src="/branding/hilalone-icon-standard-96.png"
                  alt="Ikon HILALONE"
                  width={40}
                  height={40}
                  loading="lazy"
                />
              </picture>
              <div>
                <div className="footer__brand-title">{siteConfig.fullTitle}</div>
                <div className="footer__brand-meta">
                  Versi {siteConfig.version} ({siteConfig.mvpStage})
                </div>
              </div>
            </div>
            <p className="footer__desc">
              Filosofi pengembangan: &ldquo;{siteConfig.philosophy}&rdquo; — pengolahan citra
              astronomi yang menjaga integritas data linear dari hulu hingga ekspor.
            </p>
          </div>

          <div>
            <h2 className="footer__heading">Navigasi</h2>
            <ul className="footer__links">
              <li>
                <a href="#fitur">Fitur Utama</a>
              </li>
              <li>
                <a href="#alur-kerja">Alur Kerja Pipeline</a>
              </li>
              <li>
                <a href="#antarmuka">Pratinjau Antarmuka</a>
              </li>
              <li>
                <a href="#tentang">Tentang HILALONE</a>
              </li>
              <li>
                <a href="#integritas">Integritas Ilmiah</a>
              </li>
              <li>
                <a href="#spesifikasi">Spesifikasi Teknis</a>
              </li>
              <li>
                <a href="#roadmap">Roadmap</a>
              </li>
            </ul>
          </div>

          <div>
            <h2 className="footer__heading">Sumber &amp; Dokumentasi</h2>
            <ul className="footer__links">
              {siteConfig.repoIsPublic ? (
                <li>
                  <a href={siteConfig.githubUrl} target="_blank" rel="noopener noreferrer">
                    GitHub Repository
                  </a>
                </li>
              ) : null}
              {siteConfig.repoIsPublic ? (
                <li>
                  <a
                    href={`${siteConfig.githubUrl}/blob/main/BUILD_README.md`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Dokumentasi Build &amp; Arsitektur
                  </a>
                </li>
              ) : null}
              {siteConfig.repoIsPublic && siteConfig.releasePageUrl ? (
                <li>
                  <a href={siteConfig.releasePageUrl} target="_blank" rel="noopener noreferrer">
                    Release Notes (GitHub Releases)
                  </a>
                </li>
              ) : null}
              <li>
                <a href="#unduh">Distribusi Windows v{siteConfig.version}</a>
              </li>
              <li>
                <a href="#faq">FAQ</a>
              </li>
            </ul>
          </div>
        </div>

        <div className="footer__bottom">
          <span>
            &copy; {siteConfig.copyrightYear} {siteConfig.copyrightHolder}. Seluruh hak cipta sesuai
            lisensi proyek.
          </span>
          <span>HILALONE — {siteConfig.tagline}</span>
        </div>
      </div>
    </footer>
  );
}
