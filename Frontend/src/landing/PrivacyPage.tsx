import type { ReactNode } from 'react'
import { AuthFrame } from '../app/AuthFrame.tsx'
import { Mark } from '../ui/Mark.tsx'

// The privacy policy Google's consent screen links to. It describes what the code does today: Google sign-in,
// chats and datasets stored with the account, and the services that read requests and pages. Update it (and
// UPDATED) whenever what is stored or who receives it changes.
const CONTACT = 'harshitsinhchauhan250@gmail.com'
const UPDATED = '9 October 2026'

// Inline links: underline from AuthCallback's "Try again", highlighter on hover from the Footer.
const linkClass =
  'group rounded-sm font-semibold text-ink underline decoration-2 underline-offset-4 active:text-ink-2 ' +
  'focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink'

function TextLink({ href, children }: { href: string; children: ReactNode }) {
  const external = href.startsWith('http')
  return (
    <a href={href} className={linkClass} {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}>
      <Mark on={false} className="group-hover:mark-on group-focus-visible:mark-on">
        {children}
      </Mark>
    </a>
  )
}

const mail = <TextLink href={`mailto:${CONTACT}`}>{CONTACT}</TextLink>

const SECTIONS: { title: string; body: ReactNode }[] = [
  {
    title: 'What you share when you sign in',
    body: (
      <p>
        AWDAX signs you in with Google. With your permission, Google shares your name, email address, profile
        picture and Google account ID. AWDAX uses them to create your account and to show who is signed in. It never
        sees your Google password and gets no access to your email, files or contacts.
      </p>
    ),
  },
  {
    title: 'What stays in your browser',
    body: (
      <p>
        To keep you signed in, your browser stores a session token in local storage. Signing out removes it. Your
        browser also keeps your own view settings for each chat (saved questions, dashboard layout, charts, which
        pages you opened, alerts), kept apart for each account that signs in on it. Files you upload as data stay in
        your browser. This site sets no advertising or analytics cookies.
      </p>
    ),
  },
  {
    title: 'What you create in the app',
    body: (
      <p>
        Your chats are stored with your account on AWDAX’s server so you can come back to them: what you asked for,
        the plan, the sources AWDAX read and the dataset it built. Nobody else can see them. When you ask a question
        about a table, the table and your question are sent to AWDAX’s server to work out the answer; that includes
        a table from a file you uploaded.
      </p>
    ),
  },
  {
    title: 'Who handles it',
    body: (
      <>
        <p>
          Supabase runs sign-in and stores your account in its Mumbai region. Google shows the sign-in screen.
          AWDAX runs this website and its server itself. Google Fonts serves its typefaces, so your browser contacts
          Google for them. Supabase, the AWDAX server and Google keep short-lived technical logs, such as IP addresses
          and browser details, to run the service and block abuse.
        </p>
        <p className="mt-3">
          To do the work, AWDAX sends your request, and the text of the public web pages it reads for you, to its AI
          providers (NVIDIA and Google Gemini), and search queries made from your request to its search providers
          (Serper, Tavily or Google Search). For a request about local businesses it also sends the search, and the
          location your browser shares if you allow it, to Google Maps. The pages it reads see AWDAX’s server, not you.
          It only reads pages a site allows crawlers to read.
        </p>
        <p className="mt-3">AWDAX does not sell your data or share it with advertisers.</p>
      </>
    ),
  },
  {
    title: 'Deleting your data',
    body: (
      <p>
        Deleting a chat in the app removes it, its request and the data found for it from AWDAX’s server. Your account
        stays while you have one: email {mail} and your account, and everything linked to it, will be deleted. You
        can also remove AWDAX’s access at any time from your Google account’s{' '}
        <TextLink href="https://myaccount.google.com/connections">third-party connections</TextLink> page.
      </p>
    ),
  },
  {
    title: 'Questions',
    body: <p>Write to {mail}. If this policy changes, the date at the top changes with it.</p>,
  },
]

export default function PrivacyPage() {
  return (
    <AuthFrame>
      <p className="font-mono text-micro text-ink-3">Privacy · updated {UPDATED}</p>
      <h1 className="mt-4 font-display font-wide text-section font-extrabold">
        What AWDAX <Mark>keeps about you.</Mark>
      </h1>
      <p className="mt-5 max-w-[46ch] text-lead text-ink-2">
        AWDAX turns a plain-English request into a dataset where every value shows its source. This page says what
        it stores about the people who use it, and why.
      </p>

      <div className="mt-12 border-b-2 border-ink">
        {SECTIONS.map((s) => (
          <section key={s.title} className="border-t-2 border-ink py-5">
            <h2 className="text-h3 font-bold text-ink">{s.title}</h2>
            <div className="mt-3 max-w-[62ch] text-body text-ink-2">{s.body}</div>
          </section>
        ))}
      </div>
    </AuthFrame>
  )
}
