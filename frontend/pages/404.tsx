import Link from "next/link";

export default function NotFoundPage() {
  return (
    <main className="page not-found-page">
      <section className="empty-state surface">
        <p className="eyebrow">404</p>
        <h1>This trail ends here</h1>
        <p>The page may have moved, but your repository analysis is still available.</p>
        <div className="empty-actions">
          <Link className="primary-button" href="/roadmap">Open roadmap</Link>
          <Link className="secondary-button" href="/connect">Return to Connect</Link>
        </div>
      </section>
    </main>
  );
}
