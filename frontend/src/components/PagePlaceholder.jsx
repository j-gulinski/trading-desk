export default function PagePlaceholder({ note = 'Coming in a later phase.' }) {
  return (
    <section className="page">
      <div className="page__placeholder">{note}</div>
    </section>
  )
}
