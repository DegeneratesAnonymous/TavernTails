import React, { useState } from 'react'
import { buildApiUrl } from '../api'

export default function RollPanel() {
  const [expr, setExpr] = useState('1d20')
  const [result, setResult] = useState<any>(null)

  async function roll() {
    try {
      const res = await fetch(buildApiUrl('/rolls'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expression: expr }) })
      const j = await res.json()
      setResult(j.result)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div style={{ padding: 12 }}>
      <h3>Dice Roll</h3>
      <input value={expr} onChange={e => setExpr(e.target.value)} />
      <button onClick={roll}>Roll</button>
      {result && (
        <div>
          <div>Expression: {result.expression}</div>
          <div>Rolls: {JSON.stringify(result.rolls)}</div>
          <div>Modifier: {result.mod}</div>
          <div>Total: {result.total}</div>
        </div>
      )}
    </div>
  )
}
