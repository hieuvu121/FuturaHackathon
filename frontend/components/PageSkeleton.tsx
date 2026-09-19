export default function PageSkeleton({ label = "Loading page" }: { label?: string }) {
  return (
    <main className="page page-skeleton" aria-busy="true" aria-label={label}>
      <span className="sr-only">{label}</span>
      <div className="skeleton-line skeleton-eyebrow" />
      <div className="skeleton-line skeleton-title" />
      <div className="skeleton-line skeleton-copy" />
      <div className="skeleton-grid" aria-hidden="true">
        <div className="skeleton-panel" />
        <div className="skeleton-panel" />
        <div className="skeleton-panel" />
      </div>
    </main>
  );
}
