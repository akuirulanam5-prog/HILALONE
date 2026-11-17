import { useState } from "react";
import { Check, Clock, Copy, Download, ExternalLink, ShieldAlert } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { siteConfig } from "../data/siteConfig";

export function DownloadSection() {
  const ready = siteConfig.downloadAvailable && siteConfig.downloadUrl !== null;
  const [copied, setCopied] = useState(false);

  const handleCopySha = async () => {
    if (!siteConfig.sha256 || typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(siteConfig.sha256);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section id="unduh" className="download-band">
      <div className="container">
        <div className="download-card__grid">
          <div>
            <SectionHeader
              eyebrow="Distribusi Aplikasi Desktop"
              title={`${siteConfig.appName} v${siteConfig.version} — Windows Desktop`}
              subtitle="Halaman distribusi resmi installer Windows. Tautan hanya diaktifkan setelah aset rilis resmi dan checksum SHA-256 diterbitkan."
              icon={<Download size={14} aria-hidden="true" />}
            />

            {ready && siteConfig.downloadUrl ? (
              <div className="download-actions">
                <a
                  href={siteConfig.downloadUrl}
                  className="btn btn--primary"
                  download={siteConfig.installerFilename}
                  rel="noopener noreferrer"
                >
                  <Download size={18} aria-hidden="true" />
                  <span>Unduh {siteConfig.installerFilename}</span>
                </a>

                {siteConfig.repoIsPublic ? (
                  <a
                    href={siteConfig.releasePageUrl ?? siteConfig.githubUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn--navy-outline"
                  >
                    <span>Lihat GitHub Releases</span>
                    <ExternalLink size={16} aria-hidden="true" />
                  </a>
                ) : null}
              </div>
            ) : (
              <div>
                <div className="notice-banner notice-banner--dark" role="status">
                  <Clock size={18} className="notice-banner__icon" aria-hidden="true" />
                  <div>
                    <strong>Installer HILALONE v{siteConfig.version} sedang dipersiapkan.</strong>{" "}
                    Build executable <code>ONE-DIR</code> telah selesai diuji di lingkungan
                    pengembangan terisolasi; paket installer resmi (
                    <code>{siteConfig.installerFilename}</code>) akan ditautkan di sini setelah
                    diterbitkan di GitHub Releases.
                  </div>
                </div>

                <div className="download-actions">
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled
                    aria-disabled="true"
                    title="Installer resmi belum tersedia untuk diunduh"
                  >
                    <Download size={18} aria-hidden="true" />
                    <span>Unduh Installer (Belum Tersedia)</span>
                  </button>

                  {siteConfig.repoIsPublic ? (
                    <a
                      href={siteConfig.githubUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn--navy-outline"
                    >
                      <span>Lihat Repositori GitHub</span>
                      <ExternalLink size={16} aria-hidden="true" />
                    </a>
                  ) : null}
                </div>
              </div>
            )}
          </div>

          <div>
            <dl className="download-meta-grid">
              <div>
                <dt className="meta-kv__k">Versi Rilis</dt>
                <dd className="meta-kv__v">
                  v{siteConfig.version} ({siteConfig.mvpStage})
                </dd>
              </div>
              <div>
                <dt className="meta-kv__k">Nama Installer</dt>
                <dd className="meta-kv__v meta-kv__mono">{siteConfig.installerFilename}</dd>
              </div>
              <div>
                <dt className="meta-kv__k">Ukuran Berkas</dt>
                <dd className="meta-kv__v">
                  {siteConfig.fileSize ?? "Menunggu kompilasi installer"}
                </dd>
              </div>
              <div>
                <dt className="meta-kv__k">Tanggal Rilis</dt>
                <dd className="meta-kv__v">
                  {siteConfig.releaseDate ?? "Menunggu penerbitan resmi"}
                </dd>
              </div>
              <div className="download-meta-grid__full">
                <dt className="meta-kv__k">Dukungan Windows</dt>
                <dd className="meta-kv__v">{siteConfig.supportedWindows}</dd>
              </div>
              <div className="download-meta-grid__full">
                <div className="meta-kv__head-row">
                  <dt className="meta-kv__k">SHA-256 Checksum</dt>
                  {siteConfig.sha256 ? (
                    <button type="button" className="copy-sha-btn" onClick={handleCopySha}>
                      {copied ? (
                        <>
                          <Check size={14} aria-hidden="true" />
                          <span>Tersalin</span>
                        </>
                      ) : (
                        <>
                          <Copy size={14} aria-hidden="true" />
                          <span>Salin SHA-256</span>
                        </>
                      )}
                    </button>
                  ) : null}
                </div>
                <dd className="meta-kv__v meta-kv__sha">
                  {siteConfig.sha256 ?? "Akan diterbitkan bersama berkas installer resmi"}
                </dd>
                <span className="visually-hidden" aria-live="polite">
                  {copied ? "Hash SHA-256 berhasil disalin ke papan klip." : ""}
                </span>
              </div>
            </dl>

            <div className="download-footnote">
              <ShieldAlert size={16} className="download-footnote__icon" aria-hidden="true" />
              <span>
                Catatan rilis: instalasi default diarahkan ke profil pengguna (per-user) tanpa
                menghapus konfigurasi atau log pengguna saat pencopotan aplikasi. Aplikasi juga
                dilengkapi fitur <strong>Check for Updates</strong> otomatis via GitHub Releases.
              </span>
            </div>

            {siteConfig.releaseHighlights && siteConfig.releaseHighlights.length > 0 ? (
              <div className="download-footnote" style={{ marginTop: "0.75rem", display: "block" }}>
                <strong style={{ display: "block", marginBottom: "0.35rem" }}>
                  Apa yang Baru di HILALONE v{siteConfig.version}:
                </strong>
                <ul style={{ margin: 0, paddingLeft: "1.15rem", display: "grid", gap: "0.25rem" }}>
                  {siteConfig.releaseHighlights.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
