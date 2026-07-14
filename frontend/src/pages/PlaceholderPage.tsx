export function PlaceholderPage({ title }: { title: string; sprint?: number }) {
  return (
    <section aria-labelledby="placeholder-title">
      <div className="page-header">
        <div className="page-title-block">
          <h1 id="placeholder-title">{title}</h1>
          <p>Fonctionnalité planifiée</p>
        </div>
      </div>
      <p className="intro">Cette page sera intégrée ultérieurement, comme prévu.</p>
    </section>
  );
}
