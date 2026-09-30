import { defineSample } from './build.ts'
import type { RowSpec } from './build.ts'

type Sponsorship = [company: string, event: string, tier: string, date: string, slug: string]

const TIER_WORDS: Record<string, string> = {
  Title: 'Title sponsor',
  Gold: 'Gold sponsor',
  Silver: 'Silver sponsor',
  Community: 'Community partner',
  'In-kind': 'Cloud credits partner',
}

function sponsor(src: 'eventgrid' | 'hackboard' | 'festpages', s: Sponsorship, extra: Partial<RowSpec> = {}): RowSpec {
  const [company, event, tier, date, slug] = s
  const eventSlug = event.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const structured = src === 'eventgrid'
  return {
    src,
    path: src === 'eventgrid' ? `/events/${eventSlug}` : src === 'hackboard' ? `/h/${eventSlug}/sponsors` : `/${eventSlug}`,
    ...extra,
    fields: {
      company: [company, structured ? `"sponsor": { "name": "${company}" }` : `${company} logo, alt text "${company}"`],
      event: [event, structured ? `"name": "${event}"` : `${event} · Sponsors`],
      tier: [tier, structured ? `"sponsorTier": "${tier}"` : `${TIER_WORDS[tier]}`, src === 'festpages' ? 'medium' : 'high'],
      date: [date, structured ? `"startDate": "${date}"` : `Happening on ${date}`],
      contact_page: [`https://${slug}.example/partnerships`, `Partner with us → ${slug}.example/partnerships`, 'medium'],
    },
  }
}

export const sponsors = defineSample({
  key: 'sponsors',
  label: 'Sponsors',
  text: 'Companies that sponsored student hackathons in India in 2026',
  rowLimit: 100,
  columns: [
    { key: 'company', label: 'Company', type: 'text', required: true },
    { key: 'event', label: 'Event', type: 'text', required: true },
    {
      key: 'tier',
      label: 'Tier',
      type: 'category',
      required: false,
      levels: ['Title', 'Gold', 'Silver', 'Community', 'In-kind'],
    },
    { key: 'date', label: 'Event date', type: 'date', required: true },
    { key: 'contact_page', label: 'Partnerships page', type: 'url', required: false },
  ],
  filters: [
    { column: 'event', op: 'contains', value: ['hackathon', 'hack'], label: 'Event is a hackathon run by or for students' },
    { column: 'date', op: 'between', value: ['2026-01-01', '2026-12-31'], label: 'Held in 2026' },
  ],
  interpretations: [
    {
      phrase: 'sponsored',
      readAs: 'Listed as a sponsor or partner on the event page, any tier',
      alternatives: ['Paid tiers only (Title, Gold, Silver)', 'Also include judges’ employers'],
    },
    {
      phrase: 'student hackathons',
      readAs: 'Hackathons hosted by a college or open only to students',
      alternatives: ['Any hackathon with student participants'],
    },
  ],
  sources: [
    { id: 'eventgrid', name: 'EventGrid', domain: 'eventgrid.example', permission: 'allowed', method: 'structured', health: 'ok' },
    { id: 'hackboard', name: 'HackBoard', domain: 'hackboard.example', permission: 'allowed', method: 'content', health: 'ok' },
    { id: 'festpages', name: 'College fest sites', domain: 'festpages.example', permission: 'allowed', method: 'rendered', health: 'slow' },
    {
      id: 'socialnet',
      name: 'SocialNet posts',
      domain: 'socialnet.example',
      permission: 'needs_login',
      method: 'content',
      health: 'unknown',
      note: 'Sponsor announcements are behind a sign-in wall. AWDAX does not sign in to sources.',
    },
  ],
  matchedOn: 'Same company and event',
  streamColumns: ['company', 'event', 'tier'],
  heroChart: 'tier',
  rows: [
    sponsor('eventgrid', ['Cloudnest', 'Code Monsoon 2026', 'Title', '2026-01-17', 'cloudnest'], { also: ['hackboard'] }),
    sponsor('eventgrid', ['Bytewise', 'Code Monsoon 2026', 'Gold', '2026-01-17', 'bytewise']),
    sponsor('hackboard', ['Pixelmint', 'BuildSprint Chennai', 'Silver', '2026-02-21', 'pixelmint']),
    sponsor('hackboard', ['Quanta Rails', 'BuildSprint Chennai', 'Gold', '2026-02-21', 'quantarails']),
    sponsor('festpages', ['Stackwell', 'HackTheDeccan', 'Community', '2026-03-14', 'stackwell']),
    sponsor('eventgrid', ['Dataforge', 'HackTheDeccan', 'Title', '2026-03-14', 'dataforge'], { also: ['festpages'] }),
    sponsor('hackboard', ['Loopline', 'Innov8 Kolkata', 'Silver', '2026-04-04', 'loopline']),
    sponsor('eventgrid', ['Greenbyte', 'Innov8 Kolkata', 'In-kind', '2026-04-04', 'greenbyte']),
    sponsor('festpages', ['Tessel Systems', 'DevRush Jaipur', 'Gold', '2026-05-09', 'tesselsystems']),
    sponsor('hackboard', ['Cloudnest', 'DevRush Jaipur', 'In-kind', '2026-05-09', 'cloudnest']),
    sponsor('eventgrid', ['Kernel & Co', 'Hack Konkan', 'Silver', '2026-08-22', 'kernelandco'], {
      conflicts: { tier: { src: 'festpages', path: '/hack-konkan', value: 'Gold', quote: 'Gold sponsor' } },
    }),
    sponsor('hackboard', ['Bytewise', 'Hack Konkan', 'Community', '2026-08-22', 'bytewise']),
    sponsor('festpages', ['Vantage Grid', 'Campus Commit Delhi', 'Silver', '2026-09-12', 'vantagegrid']),
    sponsor('eventgrid', ['Pixelmint', 'Campus Commit Delhi', 'Title', '2026-09-12', 'pixelmint'], { also: ['hackboard'] }),
  ],
  rejected: [
    { sourceId: 'eventgrid', label: 'Cloudnest · CloudConf 2026', reason: 'A conference, not a hackathon' },
    { sourceId: 'festpages', label: 'Bytewise · Code Monsoon 2025', reason: 'Held in 2025' },
  ],
})
