import type { ReactNode } from 'react'
import { AuthFrame } from '../app/AuthFrame.tsx'
import { Mark } from '../ui/Mark.tsx'

// The privacy policy Google's consent screen links to. It describes what the code does today: Google
// sign-in through Supabase and nothing else. Update it (and UPDATED) before shipping anything that
// stores more, such as saved requests, datasets or analytics.
const CONTACT = 'harshitsinhchauhan250@gmail.com'
const UPDATED = '27 September 2026'

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
        To keep you signed in, your browser stores a session token in local storage. Signing out removes it. This
        site sets no advertising or analytics cookies.
      </p>
    ),
  },
  {
    title: 'What you create in the app',
    body: (
      <p>
        For now the app only signs you in. When the request, plan and dataset screens open, what you create there
        will be stored with your account so you can come back to it. This page will say so before that happens.
      </p>
    ),
  },
  {
    title: 'Who handles it',
    body: (
      <>
        <p>
          Supabase runs sign-in and stores your account in its Mumbai region. Google shows the sign-in screen.
          AWDAX runs this website and its server itself. Supabase and the AWDAX server keep short-lived technical logs,
          such as IP addresses and browser details, to run the service and block abuse.
        </p>
        <p className="mt-3">AWDAX does not sell your data or share it with advertisers.</p>
      </>
    ),
  },
  {
    title: 'Deleting your data',
    body: (
      <p>
        Your account data stays while you have an account. Email {mail} and your account, and everything linked to
        it, will be deleted. You can also remove AWDAX’s access at any time from your Google account’s{' '}
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
