import { defineSample } from './build.ts'
import type { RowSpec } from './build.ts'

// Compact row helper: every lead has the same six columns, and the quote shapes repeat per source.
type Lead = [
  company: string,
  founders: string[] | null,
  amountUsd: number,
  roundDate: string,
  investors: string[],
  slug: string,
]

const fmtUsd = (n: number) => `$${(n / 1_000_000).toFixed(1)} million`
const fmtDay = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })

function lead(src: 'fundwire' | 'startupdesk' | 'newsroom', l: Lead, extra: Partial<RowSpec> = {}): RowSpec {
  const [company, founders, amount, date, investors, slug] = l
  const path = src === 'fundwire' ? `/2026/${slug}-raises-seed` : src === 'startupdesk' ? `/startups/${slug}` : `/${slug}/press`
  const founderQuote = founders && `founded by ${founders.join(' and ')}`
  return {
    src,
    path,
    ...extra,
    fields: {
      company: [company, src === 'fundwire' ? `"about": { "name": "${company}" }` : `${company} has raised`],
      founders: founders && [founders, founderQuote!, src === 'newsroom' ? 'medium' : 'high'],
      amount_usd: [amount, `raised ${fmtUsd(amount)} in a seed round`],
      round_date: [date, `Announced ${fmtDay(date)}`],
      investors: [investors, `led by ${investors.join(', with participation from ')}`],
      website: [`https://${slug}.example`, `Website: ${slug}.example`],
    },
  }
}

export const leads = defineSample({
  key: 'leads',
  label: 'Sales leads',
  text: 'Seed-stage fintech startups in India funded in 2026, with founders and amount',
  rowLimit: 100,
  columns: [
    { key: 'company', label: 'Company', type: 'text', required: true },
    { key: 'founders', label: 'Founders', type: 'list', required: false },
    { key: 'amount_usd', label: 'Amount', type: 'money', required: true, currency: 'USD' },
    { key: 'round_date', label: 'Announced', type: 'date', required: true },
    { key: 'investors', label: 'Investors', type: 'list', required: false },
    { key: 'website', label: 'Website', type: 'url', required: false },
  ],
  filters: [
    { column: 'round_date', op: 'between', value: ['2026-01-01', '2026-12-31'], label: 'Announced in 2026' },
    { column: 'company', op: 'eq', value: 'fintech', label: 'Sector is fintech' },
    { column: 'amount_usd', op: 'lte', value: 4_000_000, label: 'Round is seed stage (up to $4 million)' },
  ],
  interpretations: [
    {
      phrase: 'seed-stage',
      readAs: 'Rounds announced as seed, up to $4 million',
      alternatives: ['Also include pre-seed', 'Any round labelled seed, whatever the size'],
    },
    {
      phrase: 'in India',
      readAs: 'Headquartered in India',
      alternatives: ['Founded in India, headquartered anywhere'],
    },
  ],
  sources: [
    { id: 'fundwire', name: 'FundWire', domain: 'fundwire.example', permission: 'allowed', method: 'structured', health: 'ok' },
    { id: 'startupdesk', name: 'StartupDesk', domain: 'startupdesk.example', permission: 'allowed', method: 'content', health: 'ok' },
    { id: 'newsroom', name: 'Company press pages', domain: 'newsroomhub.example', permission: 'allowed', method: 'ai', health: 'ok' },
    {
      id: 'ledgerbase',
      name: 'Ledgerbase',
      domain: 'ledgerbase.example',
      permission: 'robots_disallowed',
      method: 'content',
      health: 'unknown',
      note: 'robots.txt disallows /companies/ for automated agents.',
    },
  ],
  matchedOn: 'Same company and website',
  streamColumns: ['company', 'amount_usd', 'round_date'],
  heroChart: 'round_date',
  rows: [
    lead('fundwire', ['Paisaloop', ['Aditi Rao', 'Karan Mehta'], 1_800_000, '2026-01-14', ['Northbeam Ventures', 'Kite Capital'], 'paisaloop'], { also: ['startupdesk'] }),
    lead('startupdesk', ['Credisync', ['Rohan Iyer'], 2_500_000, '2026-02-03', ['Monsoon Partners'], 'credisync']),
    lead('fundwire', ['Tijori Labs', ['Meera Nair'], 3_000_000, '2026-02-24', ['Kite Capital', 'Banyan Seed'], 'tijorilabs']),
    lead('fundwire', ['Ledgerleaf', ['Sana Qureshi', 'Vikram Bhat'], 1_200_000, '2026-03-11', ['Arcfield Capital'], 'ledgerleaf'], {
      conflicts: {
        amount_usd: { src: 'newsroom', path: '/ledgerleaf/press', value: 1_500_000, quote: 'raised $1.5 million in a seed round' },
      },
    }),
    lead('startupdesk', ['Rupeegrid', ['Farhan Ali'], 2_100_000, '2026-04-08', ['Northbeam Ventures'], 'rupeegrid']),
    lead('newsroom', ['UPIstack', ['Arjun Das', 'Neha Kulkarni'], 900_000, '2026-04-29', ['Chai Angels'], 'upistack']),
    lead('fundwire', ['Kosh Finance', ['Ishita Sen', 'Dev Malhotra'], 1_500_000, '2026-05-06', ['Arcfield Capital', 'Tidewater'], 'koshfinance'], { also: ['newsroom'] }),
    lead('startupdesk', ['Nivesh Pilot', null, 1_100_000, '2026-05-19', ['Banyan Seed'], 'niveshpilot']),
    lead('fundwire', ['Bahi Books', ['Anjali Gupta'], 2_800_000, '2026-05-28', ['Monsoon Partners', 'Kite Capital'], 'bahibooks']),
    lead('newsroom', ['Kharcha', ['Siddharth Rao', 'Pooja Jain'], 1_600_000, '2026-06-17', ['Chai Angels'], 'kharcha']),
    lead('startupdesk', ['Hisaab Pay', ['Nikhil Bose'], 2_200_000, '2026-06-30', ['Tidewater'], 'hisaabpay'], { also: ['fundwire'] }),
    lead('fundwire', ['Dhanvest', ['Kavya Reddy', 'Aman Shah'], 3_500_000, '2026-07-22', ['Northbeam Ventures'], 'dhanvest']),
    lead('startupdesk', ['Bachat Box', ['Tanvi Joshi'], 750_000, '2026-08-05', ['Chai Angels', 'Banyan Seed'], 'bachatbox']),
    lead('fundwire', ['Rokda Cloud', ['Yash Agarwal'], 1_900_000, '2026-08-26', ['Arcfield Capital'], 'rokdacloud']),
    lead('newsroom', ['Sanchay', ['Riya Kapoor', 'Mohit Verma'], 2_400_000, '2026-09-09', ['Kite Capital'], 'sanchay']),
  ],
  rejected: [
    { sourceId: 'fundwire', label: 'Paymint · $12 million Series A', reason: 'Series A, not seed' },
    { sourceId: 'startupdesk', label: 'Greenfield Agro · seed', reason: 'Agritech, not fintech' },
    { sourceId: 'newsroom', label: 'Coinward · seed', reason: 'Headquartered in Singapore' },
  ],
})
