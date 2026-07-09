export async function getStatus() {
  const res = await fetch('/monitoring/status')
  if (!res.ok) throw new Error(`GET /monitoring/status failed: ${res.status}`)
  return res.json()
}
