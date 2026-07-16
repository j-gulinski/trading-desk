export default function Panel({ title, meta, children }) {
  return (
    <section className="panel">
      <header className="panel__head">
        <span className="panel__title">{title}</span>
        {meta != null && <span className="panel__meta">{meta}</span>}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  )
}
