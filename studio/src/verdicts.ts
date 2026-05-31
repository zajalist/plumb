import data from './verdicts.json'

/** One gate result inside a Verdict (mirrors contracts.GateResult). */
export type Gate = {
  gate: 'collision' | 'stability' | 'constraints' | 'reach'
  ok: boolean | null
  skipped: boolean
  value_m: number | null
  fix: number[] | null
  viz: string | null
  detail: string | null
}

/** One agent attempt = one Verdict, as produced by the conscience demo. */
export type Attempt = {
  attempt: number
  ok: boolean
  stopped_at: string | null
  soft_cost: number
  committed: boolean
  gates: Gate[]
}

export const attempts = data as Attempt[]
