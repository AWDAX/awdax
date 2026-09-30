import { jobs } from './jobs.ts'
import { leads } from './leads.ts'
import { market } from './market.ts'
import { sponsors } from './sponsors.ts'
import type { SampleKey, SampleRun } from './build.ts'

export type { SampleKey, SampleRun } from './build.ts'

/** In preset order. */
export const samples: SampleRun[] = [leads, jobs, sponsors, market]

export const sampleByKey: Record<SampleKey, SampleRun> = { jobs, leads, sponsors, market }
