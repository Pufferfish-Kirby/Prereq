import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './App.css'

// ── Shared markdown render config ───────────────────────────────────────────
// Extracted to module scope (not redefined per-render) so BOTH the live
// typewriter reveal and the settled/history render use byte-for-byte identical
// styling. WHY this matters: if the typewriter and final render used different
// component maps, finished messages would visibly "jump" in styling the instant
// animation completed. Defining it once guarantees they don't.
const MARKDOWN_COMPONENTS = {
  p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc list-inside space-y-0.5 my-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside space-y-0.5 my-1">{children}</ol>,
  h1: ({ children }) => <h1 className="font-bold text-base mt-2 mb-1">{children}</h1>,
  h2: ({ children }) => <h2 className="font-semibold text-sm mt-2 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="font-medium text-sm mt-1 mb-0.5">{children}</h3>,
  code: ({ children }) => <code className="bg-white/10 rounded px-1 py-0.5 text-xs font-mono">{children}</code>,
  // WHY a custom li renderer: remark-gfm can emit list items with empty
  // content when markdown has trailing `- ` bullet lines or whitespace-only
  // entries. Without this guard those render as blank `• ` dots in the UI.
  // We coerce children to a string to handle both plain text and nested
  // React element arrays, then bail out (return null) if nothing printable.
  li: ({ children }) => {
    const text = typeof children === 'string' ? children : Array.isArray(children) ? children.join('') : String(children ?? '')
    if (!text.trim()) return null
    return <li>{children}</li>
  },
}

// ── TypewriterMarkdown ──────────────────────────────────────────────────────
// Renders an assistant reply either instantly (history) or with a ChatGPT-style
// progressive word reveal (fresh replies).
//
// HOW the `animate` flag drives behaviour:
//   - animate === false  → render the full ReactMarkdown immediately. This is
//     the path for messages restored from a past session via loadChat, which
//     carry no `animate` flag, so they never re-type.
//   - animate === true   → reveal a growing prefix of the text a few words per
//     tick with a blinking caret, THEN, once the whole string is shown, fall
//     through to the same full ReactMarkdown render. We reveal as plain text
//     mid-stream (not markdown) because partial markdown is often malformed
//     (an open ** or half a list), which would flicker; once complete we hand
//     off to the real markdown renderer so the final styling is correct.
function TypewriterMarkdown({ content, animate, onReveal }) {
  // visibleCount = how many words of `content` are currently shown.
  // Start fully revealed when not animating so static messages paint at once.
  const words = content.split(/(\s+)/) // keep whitespace tokens so spacing is preserved
  const [visibleCount, setVisibleCount] = useState(animate ? 0 : words.length)
  const [done, setDone] = useState(!animate)

  useEffect(() => {
    if (!animate) return // history / already-settled: nothing to schedule

    let count = 0
    // ~3 word-tokens per tick at 40ms ≈ ChatGPT's perceived pace. Stepping by
    // chunks (not one char) keeps it lively without thrashing React renders.
    const CHUNK = 3
    const TICK_MS = 40
    const timer = setInterval(() => {
      count += CHUNK
      if (count >= words.length) {
        setVisibleCount(words.length)
        setDone(true)
        clearInterval(timer)
      } else {
        setVisibleCount(count)
      }
      // Notify the parent each tick so it can keep the view scrolled to the
      // bottom as the text grows (the `messages` array doesn't change during
      // typing, so the parent's normal scroll effect wouldn't fire on its own).
      onReveal?.()
    }, TICK_MS)

    // CRITICAL cleanup: clear the interval if the component unmounts (e.g. the
    // user switches sessions mid-type) so we never call setState on an unmounted
    // component or leak a runaway timer.
    return () => clearInterval(timer)
    // Re-run only if the message identity changes. content+animate are stable
    // for a given bubble, so this effect runs once per fresh reply.
  }, [content, animate, words.length])

  // Once fully revealed, render the real markdown so final styling is exact.
  if (done) {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {content}
      </ReactMarkdown>
    )
  }

  // Mid-reveal: show the plain-text prefix plus a blinking caret.
  return (
    <span className="whitespace-pre-wrap">
      {words.slice(0, visibleCount).join('')}
      <span className="typewriter-cursor">▍</span>
    </span>
  )
}

// Workload maps weekly effort preference to the 1–5 integer scale the backend uses.
// 1 = very light, 5 = very heavy — stored as numbers so they feed directly into scoring.
const WORKLOAD_OPTIONS = [
  { value: '', label: 'Select a workload...' },
  { value: 2, label: 'Light' },
  { value: 3, label: 'Standard' },
  { value: 5, label: 'Heavy' },
]

// Difficulty maps how challenging the student wants courses to the 1–10 scale the backend uses.
const DIFFICULTY_OPTIONS = [
  { value: '', label: 'Select a difficulty...' },
  { value: 2, label: 'Easy' },
  { value: 5, label: 'Medium' },
  { value: 8, label: 'Hard' },
]

function App() {
  // Which view is active. Defaults to 'home' so first-time visitors land on the
  // marketing/explainer page rather than being dropped straight into a form.
  // Values: 'home' | 'planner' | 'chat' | 'reviews'.
  const [activeTab, setActiveTab] = useState('home')

  // ── Planner tab state ──
  const [interests, setInterests] = useState('')
  const [workload, setWorkload] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [submitted, setSubmitted] = useState(null)
  const [courses, setCourses] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // ── Chat tab state ──
  // messages is the full conversation history shown in the UI and sent to /chat
  // so the backend can give context-aware responses across multiple turns.
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState(null)

  // chatSessions is the list shown in the sidebar — loaded from SQLite via /chats.
  // currentSessionId tracks which session is open so we can tag outgoing messages
  // with the right session_id for server-side persistence.
  const [chatSessions, setChatSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)

  // ── Reviews tab state ──
  const [reviewCourseCode, setReviewCourseCode] = useState('')
  const [reviewRating, setReviewRating] = useState(5)
  const [reviewText, setReviewText] = useState('')
  const [reviewSubmitting, setReviewSubmitting] = useState(false)
  const [reviewSubmitMsg, setReviewSubmitMsg] = useState(null)
  const [reviewLookupCode, setReviewLookupCode] = useState('')
  const [reviewResults, setReviewResults] = useState(null)
  const [reviewLookupLoading, setReviewLookupLoading] = useState(false)

  // Ref to the bottom of the message list — we scroll to it after each new message
  // so the user always sees the latest response without manually scrolling.
  const messagesEndRef = useRef(null)
  // scrollTick is bumped by the typewriter on every reveal tick. Including it in
  // the scroll effect's deps lets us follow the growing text during typing,
  // since `messages` itself doesn't change while a single bubble is animating.
  const [scrollTick, setScrollTick] = useState(0)
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, chatLoading, scrollTick])

  // Load the session list whenever the user switches to the chat tab.
  // WHY not load at mount: the planner tab is the default, so we'd be making
  // a network request for data the user may never need.  Lazy-loading on tab
  // activation keeps startup fast.
  //
  // WHY filter to message_count > 0: sessions are created lazily (only when the
  // first message is sent), so the sidebar only ever shows conversations that
  // actually have content.  Any leftover empty sessions from earlier runs are
  // hidden without needing a DB migration.
  useEffect(() => {
    if (activeTab === 'chat') {
      fetch('http://localhost:8000/chats')
        .then(r => r.json())
        .then(sessions => setChatSessions(sessions.filter(s => s.message_count > 0)))
        .catch(() => {})
    }
  }, [activeTab])

  // Reset to a blank chat state without touching the DB.
  // The session row is created lazily when the first message is sent.
  function startNewChat() {
    setCurrentSessionId(null)
    setMessages([])
  }

  // Fetch persisted messages for a past session and restore them into the UI.
  // WHY replace messages outright instead of merging:
  //     Each session is its own isolated conversation — we never want turns
  //     from session A bleeding into session B's view.
  async function loadChat(session) {
    try {
      const res = await fetch(`http://localhost:8000/chats/${session.id}/messages`)
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const msgs = await res.json()
      setCurrentSessionId(session.id)
      setMessages(msgs)
    } catch (err) {
      setChatError(`Could not load chat: ${err.message}`)
    }
  }

  async function handleChatSend(e) {
    e.preventDefault()
    const text = inputValue.trim()
    if (!text || chatLoading) return

    // Create the DB session on the very first message.
    // WHY use a local variable instead of reading currentSessionId after setState:
    //     setCurrentSessionId is async — the state won't have updated by the time
    //     we build the fetch body below, so we capture the id here and use it directly.
    let sessionId = currentSessionId
    if (sessionId === null) {
      try {
        const res = await fetch('http://localhost:8000/chats', { method: 'POST' })
        if (!res.ok) throw new Error()
        const session = await res.json()
        sessionId = session.id
        setCurrentSessionId(session.id)
      } catch {
        setChatError('Could not create chat session. Try again.')
        return
      }
    }

    // Optimistically add the user message to the UI before the response arrives
    const userMsg = { role: 'user', content: text }
    const updatedHistory = [...messages, userMsg]
    setMessages(updatedHistory)
    setInputValue('')
    setChatError(null)
    setChatLoading(true)

    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Send the full history so Claude can refer to earlier turns.
        // We exclude the just-added userMsg from history and pass it as `message`
        // to match the ChatRequest schema: { message, history: prior turns }.
        body: JSON.stringify({
          message: text,
          history: messages, // prior turns only, not the one we just added
          session_id: sessionId,
        }),
      })

      if (!response.ok) throw new Error(`Server error: ${response.status}`)

      const data = await response.json()
      // Tag this reply with `animate: true` so TypewriterMarkdown reveals it
      // word-by-word. Replies restored from history (loadChat) never carry this
      // flag, which is exactly what keeps past sessions from re-typing.
      setMessages([...updatedHistory, { role: 'assistant', content: data.response, animate: true }])

      // Re-fetch session list so the sidebar title updates (first message auto-renames
      // the session) and the new session appears for the first time.
      fetch('http://localhost:8000/chats')
        .then(r => r.json())
        .then(sessions => setChatSessions(sessions.filter(s => s.message_count > 0)))
        .catch(() => {})
    } catch (err) {
      setChatError(err.message)
    } finally {
      setChatLoading(false)
    }
  }

  async function handleSubmit(e) {
    // Prevent the default browser form navigation
    e.preventDefault()

    // Parse interests into a clean array — trim whitespace and drop empties
    // so "  math,  cs,  " becomes ["math", "cs"] instead of a messy list.
    const parsedInterests = interests
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    setSubmitted({ interests: parsedInterests, workload, difficulty })
    setCourses(null)
    setError(null)
    setLoading(true)

    try {
      // POST to the FastAPI backend running on port 8000.
      // The body shape must match the RequestData Pydantic model in main.py:
      //   interests (list[str]), preferred_difficulty (int), preferred_workload (int)
      const response = await fetch('http://localhost:8000/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interests: parsedInterests,
          preferred_difficulty: Number(difficulty),
          preferred_workload: Number(workload),
          completed_courses: [],
        }),
      })

      if (!response.ok) {
        // Surface the HTTP error text so it's visible during development
        throw new Error(`Server error: ${response.status}`)
      }

      const data = await response.json()
      // Backend returns the array directly: [{ name, score, explanation }, ...]
      setCourses(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmitReview(e) {
    e.preventDefault()
    if (!reviewCourseCode.trim()) return
    setReviewSubmitting(true)
    setReviewSubmitMsg(null)
    try {
      const res = await fetch('http://localhost:8000/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          course_code: reviewCourseCode.trim().toUpperCase(),
          rating: reviewRating,
          review_text: reviewText,
        }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      setReviewSubmitMsg('Review submitted!')
      setReviewCourseCode('')
      setReviewRating(5)
      setReviewText('')
    } catch (err) {
      setReviewSubmitMsg(`Error: ${err.message}`)
    } finally {
      setReviewSubmitting(false)
    }
  }

  async function handleLookupReviews(e) {
    e.preventDefault()
    if (!reviewLookupCode.trim()) return
    setReviewLookupLoading(true)
    setReviewResults(null)
    try {
      const res = await fetch(`http://localhost:8000/reviews/${reviewLookupCode.trim().toUpperCase()}`)
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      setReviewResults(await res.json())
    } catch (err) {
      setReviewResults([])
    } finally {
      setReviewLookupLoading(false)
    }
  }

  return (
    // Full-height dark-blue background — this is UofT's primary brand colour (#002A5C)
    <div className="min-h-screen bg-uoft-blue flex flex-col">

      {/* ── Navbar ──
          Slightly translucent + blurred so content scrolling beneath it gives a
          subtle sense of depth, and a hairline border to separate it cleanly. */}
      <header className="sticky top-0 z-20 bg-uoft-blue/95 backdrop-blur border-b border-white/10 px-6 sm:px-8 py-3.5 flex items-center gap-3">
        {/* Logo is a real button: clicking "MyUofT" returns to the landing page,
            the conventional behaviour users expect from a product wordmark. */}
        <button
          onClick={() => setActiveTab('home')}
          className="group flex items-center gap-2.5 focus:outline-none"
          aria-label="Go to home"
        >
          {/* The accent bar carries UofT gold on hover to tie the wordmark to the
              brand accent without shouting. */}
          <span className="w-1 h-7 rounded-full bg-white group-hover:bg-uoft-accent transition-colors" />
          <span className="text-white text-xl font-semibold tracking-wide">
            My<span className="text-uoft-accent">UofT</span>
          </span>
        </button>

        {/* Tab switcher in the navbar — right-aligned. 'home' is intentionally
            omitted here; the logo is the canonical way back home, keeping the
            switcher focused on the three working tools. */}
        <nav className="ml-auto flex gap-1 bg-white/10 rounded-xl p-1 ring-1 ring-white/10">
          {['planner', 'chat', 'reviews'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`
                px-3.5 sm:px-4 py-1.5 rounded-lg text-sm font-medium transition-all
                ${activeTab === tab
                  ? 'bg-white text-uoft-blue shadow-sm'
                  : 'text-white/65 hover:text-white hover:bg-white/5'}
              `}
            >
              {tab === 'chat' ? 'AI Advisor' : tab === 'reviews' ? 'Reviews' : 'Planner'}
            </button>
          ))}
        </nav>
      </header>

      {/* ── Main content ── */}
      {/* WHY flex-col overflow-hidden instead of items-center justify-center:
          each tab now manages its own centering/scrolling so the chat panel can
          fill all remaining vertical space without fighting a fixed py-12 gutter. */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* WHY w-full with no max-w here: the chat tab needs the full width for its
            two-column layout; the planner tab constrains itself via its own wrapper. */}
        <div className="w-full flex-1 flex flex-col min-h-0">

        {/* ══════════════════════════════════════════
            HOME / LANDING VIEW
            The default view. A marketing hero + a three-card "how it works"
            strip that maps directly onto the three working tabs. Shown when
            activeTab === 'home'.
        ══════════════════════════════════════════ */}
        {activeTab === 'home' && (
          // relative + overflow-hidden so the ambient gradient glows are clipped
          // to this section and can't trigger page-level horizontal scroll.
          <div className="relative flex-1 overflow-y-auto overflow-x-hidden">

            {/* Ambient background: two soft radial glows over the flat blue give
                the hero depth/atmosphere instead of a dead solid fill. They sit
                behind content (-z) and drift slowly for a living feel. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -top-32 -left-24 w-[34rem] h-[34rem] rounded-full blur-3xl opacity-40 animate-glow-drift"
              style={{ background: 'radial-gradient(circle, #1d4f8c 0%, transparent 70%)' }}
            />
            <div
              aria-hidden="true"
              className="pointer-events-none absolute top-40 -right-32 w-[30rem] h-[30rem] rounded-full blur-3xl opacity-30 animate-glow-drift"
              style={{ background: 'radial-gradient(circle, #4BA3F5 0%, transparent 70%)', animationDelay: '4s' }}
            />

            <div className="relative max-w-5xl mx-auto px-6 py-16 sm:py-24">

              {/* ── Hero ── */}
              <div className="text-center max-w-3xl mx-auto">
                {/* Eyebrow pill. animate-fade-rise with no delay leads the
                    staggered entrance; each following element delays a little
                    more so the hero assembles top-to-bottom. */}
                <span className="animate-fade-rise inline-flex items-center gap-2 rounded-full bg-white/10 ring-1 ring-white/15 px-4 py-1.5 text-xs font-medium tracking-wide text-white/80">
                  <span className="w-1.5 h-1.5 rounded-full bg-uoft-accent" />
                  AI course planning for University of Toronto
                </span>

                <h2
                  className="animate-fade-rise mt-7 text-4xl sm:text-6xl font-bold tracking-tight text-white leading-[1.05]"
                  style={{ animationDelay: '0.08s' }}
                >
                  Turn a 20-minute conversation
                  <br className="hidden sm:block" />{' '}
                  into a <span className="text-uoft-accent">4-year plan</span>
                </h2>

                <p
                  className="animate-fade-rise mt-6 text-base sm:text-lg leading-relaxed text-white/70"
                  style={{ animationDelay: '0.16s' }}
                >
                  UofT students face thousands of courses, minors, majors and specialist
                  programs across the Faculty of Arts and Science. Parsing
                  the Academic Calendar to figure out what to take can take weeks. MyUofT
                  understands your interests, goals and degree requirements, then builds a
                  personalized long-term plan in minutes.
                </p>

                {/* CTAs: primary (white, high-contrast) routes to the Planner;
                    secondary (outlined) routes to the AI Advisor chat. */}
                <div
                  className="animate-fade-rise mt-9 flex flex-col sm:flex-row gap-3 justify-center"
                  style={{ animationDelay: '0.24s' }}
                >
                  <button
                    onClick={() => setActiveTab('planner')}
                    className="
                      group inline-flex items-center justify-center gap-2
                      bg-white text-uoft-blue font-semibold rounded-xl px-7 py-3.5 text-sm
                      shadow-lg shadow-black/20 hover:shadow-xl hover:-translate-y-0.5
                      active:translate-y-0 transition-all
                    "
                  >
                    Get Started
                    <span className="transition-transform group-hover:translate-x-0.5">→</span>
                  </button>
                  <button
                    onClick={() => setActiveTab('chat')}
                    className="
                      inline-flex items-center justify-center gap-2
                      bg-white/5 text-white font-semibold rounded-xl px-7 py-3.5 text-sm
                      ring-1 ring-white/25 hover:bg-white/10 hover:ring-white/40
                      transition-all
                    "
                  >
                    Talk to the AI Advisor
                  </button>
                </div>
              </div>

              {/* ── "How it works" / features strip ── */}
              <div
                className="animate-fade-rise mt-20 grid gap-5 sm:grid-cols-3"
                style={{ animationDelay: '0.32s' }}
              >
                {/* Each card maps one-to-one to a working tab and is clickable so
                    the strip doubles as secondary navigation. Defined inline as
                    an array so the markup stays DRY. */}
                {[
                  {
                    tab: 'planner',
                    title: 'Course Planner',
                    desc: 'Share your interests and effort level — get ranked course picks with reasons.',
                    icon: (
                      // Clipboard / checklist — represents building a plan.
                      <path d="M9 4h6a1 1 0 0 1 1 1v1h2a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h2V5a1 1 0 0 1 1-1Zm0 2v1h6V6H9Zm-1 6h2m-2 4h2m4-4h2m-2 4h2" />
                    ),
                  },
                  {
                    tab: 'chat',
                    title: 'AI Advisor',
                    desc: 'Chat through prerequisites, programs and degree planning, one question at a time.',
                    icon: (
                      // Speech bubble — represents conversation.
                      <path d="M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-4 4v-4H5a1 1 0 0 1-1-1V5Z" />
                    ),
                  },
                  {
                    tab: 'reviews',
                    title: 'Course Reviews',
                    desc: 'See what other students said, and share your own take on a course.',
                    icon: (
                      // Star — represents ratings/reviews.
                      <path d="M12 4l2.4 4.9 5.4.8-3.9 3.8.9 5.3-4.8-2.5-4.8 2.5.9-5.3L4.2 9.7l5.4-.8L12 4Z" />
                    ),
                  },
                ].map((card) => (
                  <button
                    key={card.tab}
                    onClick={() => setActiveTab(card.tab)}
                    className="
                      group text-left rounded-2xl p-6
                      bg-white/[0.06] ring-1 ring-white/10
                      hover:bg-white/[0.1] hover:ring-white/25 hover:-translate-y-1
                      shadow-lg shadow-black/10 transition-all
                    "
                  >
                    {/* Icon tile in a faint gold wash so each card has a warm focal point. */}
                    <span className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-uoft-accent/15 ring-1 ring-uoft-accent/25 text-uoft-accent">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="w-5 h-5"
                      >
                        {card.icon}
                      </svg>
                    </span>
                    <h3 className="mt-4 text-white font-semibold text-base">{card.title}</h3>
                    <p className="mt-1.5 text-white/60 text-sm leading-relaxed">{card.desc}</p>
                    <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-white/50 group-hover:text-uoft-accent transition-colors">
                      Open
                      <span className="transition-transform group-hover:translate-x-0.5">→</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════
            CHAT TAB
            Two-column layout: session sidebar + chat panel.
            Shown when activeTab === 'chat'.
        ══════════════════════════════════════════ */}
        {activeTab === 'chat' && (
          <div className="flex-1 flex gap-4 min-h-0 w-full max-w-4xl mx-auto px-4 py-6">

            {/* ── Session sidebar ── */}
            <div className="w-52 flex flex-col gap-2 shrink-0">
              <button
                onClick={startNewChat}
                className="w-full bg-white text-uoft-blue font-semibold rounded-lg py-2 text-sm hover:bg-white/90 transition"
              >
                + New Chat
              </button>
              <div className="flex-1 overflow-y-auto space-y-1">
                {chatSessions.map(session => (
                  <button
                    key={session.id}
                    onClick={() => loadChat(session)}
                    className={`
                      w-full text-left px-3 py-2 rounded-lg text-xs truncate transition
                      ${session.id === currentSessionId
                        ? 'bg-white text-uoft-blue font-medium'
                        : 'bg-white/10 text-white/70 hover:bg-white/20 hover:text-white'}
                    `}
                  >
                    {/* Use 'or' fallback so an empty title never renders a blank button */}
                    {session.title || 'New Chat'}
                  </button>
                ))}
                {chatSessions.length === 0 && (
                  <p className="text-white/30 text-xs text-center mt-4 italic">No chats yet</p>
                )}
              </div>
            </div>

            {/* ── Chat panel ── */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="text-center mb-4">
                <h2 className="text-white text-2xl font-bold tracking-tight">AI Advisor</h2>
                <p className="text-white/60 mt-1 text-xs">
                  {currentSessionId ? 'Session active — messages are saved.' : 'Type a message to start a new session.'}
                </p>
              </div>

              {/* Scrollable message list */}
              <div className="flex-1 overflow-y-auto space-y-3 pr-1 mb-4">
                {messages.length === 0 && (
                  <p className="text-white/40 text-sm text-center mt-8 italic">
                    Ask about courses, programs, prerequisites, or degree planning.
                  </p>
                )}

                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {/* Subtle shadow on both bubble types lifts the thread off
                        the flat blue and improves message separation. */}
                    <div className={`
                      max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm
                      ${msg.role === 'user'
                        ? 'bg-white text-uoft-blue rounded-br-sm'
                        : 'bg-white/15 ring-1 ring-white/10 text-white rounded-bl-sm'}
                    `}>
                      {msg.role === 'assistant'
                        ? <TypewriterMarkdown
                            content={msg.content}
                            // Only fresh replies carry animate:true (set in
                            // handleChatSend). History messages lack the flag →
                            // render instantly. Coerced to boolean so undefined
                            // (history) becomes a clean false.
                            animate={!!msg.animate}
                            onReveal={() => setScrollTick((t) => t + 1)}
                          />
                        : msg.content
                      }
                    </div>
                  </div>
                ))}

                {/* Typing indicator — shown while waiting for Claude's response */}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white/15 text-white/60 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm italic">
                      Thinking...
                    </div>
                  </div>
                )}

                {chatError && <p className="text-red-300 text-xs text-center">{chatError}</p>}

                {/* Invisible anchor we scroll into view after each message */}
                <div ref={messagesEndRef} />
              </div>

              {/* Input bar — always enabled; the session is created lazily on first send */}
              <form onSubmit={handleChatSend} className="flex gap-2">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Ask about courses, prerequisites, programs..."
                  disabled={chatLoading}
                  className="
                    flex-1 rounded-xl border border-white/20 bg-white/10 text-white
                    placeholder-white/40 px-4 py-3 text-sm
                    focus:outline-none focus:ring-2 focus:ring-white/30
                    disabled:opacity-50 transition
                  "
                />
                <button
                  type="submit"
                  disabled={chatLoading || !inputValue.trim()}
                  className="
                    bg-white text-uoft-blue font-semibold rounded-xl px-5 py-3 text-sm
                    hover:bg-white/90 active:scale-[0.97] transition-all
                    disabled:opacity-40 disabled:cursor-not-allowed
                  "
                >
                  Send
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════
            PLANNER TAB — existing form, unchanged.
            WHY max-w-lg here instead of on the outer wrapper:
                The chat tab needs the full viewport width for its two-column
                layout, so the outer div no longer carries max-w.  We restore
                the narrow constraint here so the planner form doesn't stretch.
        ══════════════════════════════════════════ */}
        {activeTab === 'planner' && (
        <div className="flex-1 flex items-start justify-center px-4 py-12 overflow-y-auto">
        <div className="w-full max-w-lg space-y-8">
        <>

          {/* Page heading */}
          <div className="text-center">
            <h2 className="text-white text-3xl font-bold tracking-tight">
              Plan Your Degree
            </h2>
            <p className="text-white/60 mt-2 text-sm">
              Tell us your interests and how hard you want to work — we'll handle the rest.
            </p>
          </div>

          {/* ── Input form ── */}
          {/* White card sits on the dark blue background for contrast */}
          {/* shadow-2xl + ring give the white form card more lift off the dark
              background; the planner is the primary CTA destination so it earns
              the strongest depth on the page. */}
          <form
            onSubmit={handleSubmit}
            className="bg-white rounded-2xl shadow-2xl ring-1 ring-black/5 p-8 space-y-6"
          >

            {/* Interests field */}
            <div className="space-y-2">
              <label
                htmlFor="interests"
                className="block text-sm font-semibold text-uoft-blue"
              >
                Interests
              </label>
              <input
                id="interests"
                type="text"
                value={interests}
                onChange={(e) => setInterests(e.target.value)}
                placeholder="e.g. machine learning, philosophy, economics"
                // Required so the browser blocks submission if left empty
                required
                className="
                  w-full rounded-lg border border-gray-200 px-4 py-3
                  text-sm text-gray-800 placeholder-gray-400
                  focus:outline-none focus:ring-2 focus:ring-uoft-blue/40 focus:border-uoft-blue
                  transition
                "
              />
              <p className="text-xs text-gray-400">
                Separate multiple interests with commas
              </p>
            </div>

            {/* Difficulty dropdown — maps to a 1–10 int for the scoring engine */}
            <div className="space-y-2">
              <label
                htmlFor="difficulty"
                className="block text-sm font-semibold text-uoft-blue"
              >
                Preferred difficulty
              </label>
              <select
                id="difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                required
                className="
                  w-full rounded-lg border border-gray-200 px-4 py-3
                  text-sm text-gray-800
                  focus:outline-none focus:ring-2 focus:ring-uoft-blue/40 focus:border-uoft-blue
                  transition appearance-none bg-white
                "
              >
                {DIFFICULTY_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value} disabled={value === ''}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {/* Workload dropdown — maps to a 1–5 int for the scoring engine */}
            <div className="space-y-2">
              <label
                htmlFor="workload"
                className="block text-sm font-semibold text-uoft-blue"
              >
                Workload preference
              </label>
              <select
                id="workload"
                value={workload}
                onChange={(e) => setWorkload(e.target.value)}
                required
                className="
                  w-full rounded-lg border border-gray-200 px-4 py-3
                  text-sm text-gray-800
                  focus:outline-none focus:ring-2 focus:ring-uoft-blue/40 focus:border-uoft-blue
                  transition appearance-none bg-white
                "
              >
                {WORKLOAD_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value} disabled={value === ''}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {/* Submit */}
            <button
              type="submit"
              className="
                w-full bg-uoft-blue text-white font-semibold rounded-lg
                py-3 text-sm tracking-wide
                hover:bg-uoft-blue/90 active:scale-[0.98]
                transition-all duration-150
                focus:outline-none focus:ring-2 focus:ring-uoft-blue/40
              "
            >
              Generate Plan →
            </button>
          </form>

          {/* ── Output panel ──
              Shown after first submit. Displays loading state, errors, and
              eventually the course list returned by the backend. */}
          {submitted && (
            <div className="bg-white/10 border border-white/20 rounded-2xl p-6 space-y-4">
              <h3 className="text-white font-semibold text-sm uppercase tracking-widest">
                Recommended Courses
              </h3>

              {loading && (
                <p className="text-white/60 text-sm italic">Loading...</p>
              )}

              {error && (
                <p className="text-red-300 text-sm">{error}</p>
              )}

              {courses && (
                <div className="space-y-3">
                  {courses.map((course) => (
                    <div
                      key={course.name}
                      className="bg-white/[0.07] ring-1 ring-white/15 rounded-xl px-4 py-3 flex items-start gap-4 hover:bg-white/10 hover:ring-white/25 transition-colors"
                    >
                      {/* Score badge in gold so the headline metric pops against
                          the blue and reuses the brand accent. */}
                      <div className="shrink-0 w-10 h-10 rounded-full bg-uoft-accent/15 ring-1 ring-uoft-accent/30 flex items-center justify-center">
                        <span className="text-uoft-accent text-xs font-bold">{course.score}</span>
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="text-white font-semibold text-sm">{course.name}</p>

                        {course.reasons && course.reasons.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {course.reasons.map((reason, idx) => (
                              <span
                                key={idx}
                                className={`
                                  inline-block rounded-full px-2.5 py-0.5 text-xs font-medium
                                  ${reason.positive
                                    ? 'bg-green-500/20 text-green-200'
                                    : 'bg-amber-500/20 text-amber-200'}
                                `}
                              >
                                {reason.message}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="text-white/60 text-xs mt-0.5">No specific reasons found.</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
        </div>
        </div>)}
        {/* end activeTab === 'planner' */}

        {/* ══════════════════════════════════════════
            REVIEWS TAB
            Two sections: submit a review + browse reviews by course code.
            Shown when activeTab === 'reviews'.
        ══════════════════════════════════════════ */}
        {activeTab === 'reviews' && (
        <div className="flex-1 flex items-start justify-center px-4 py-12 overflow-y-auto">
          <div className="w-full max-w-2xl space-y-8">

            <div className="text-center">
              <h2 className="text-white text-3xl font-bold tracking-tight">Course Reviews</h2>
              <p className="text-white/60 mt-2 text-sm">
                Share your experience or browse what other students said.
              </p>
            </div>

            {/* Submit a review */}
            <form onSubmit={handleSubmitReview} className="bg-white rounded-2xl shadow-2xl ring-1 ring-black/5 p-8 space-y-5">
              <h3 className="text-uoft-blue font-bold text-base">Leave a Review</h3>

              <div className="space-y-2">
                <label className="block text-sm font-semibold text-uoft-blue">Course Code</label>
                <input
                  type="text"
                  value={reviewCourseCode}
                  onChange={e => setReviewCourseCode(e.target.value)}
                  placeholder="e.g. CSC207H1"
                  required
                  className="w-full rounded-lg border border-gray-200 px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-uoft-blue/40 transition"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-semibold text-uoft-blue">Rating (1–5)</label>
                <div className="flex gap-2">
                  {[1,2,3,4,5].map(n => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setReviewRating(n)}
                      className={`
                        w-10 h-10 rounded-full text-sm font-bold transition-all
                        ${reviewRating >= n
                          ? 'bg-uoft-blue text-white'
                          : 'bg-gray-100 text-gray-400 hover:bg-gray-200'}
                      `}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-semibold text-uoft-blue">Your Review</label>
                <textarea
                  value={reviewText}
                  onChange={e => setReviewText(e.target.value)}
                  placeholder="What did you think of this course?"
                  rows={3}
                  className="w-full rounded-lg border border-gray-200 px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-uoft-blue/40 transition resize-none"
                />
              </div>

              <button
                type="submit"
                disabled={reviewSubmitting}
                className="w-full bg-uoft-blue text-white font-semibold rounded-lg py-3 text-sm hover:bg-uoft-blue/90 transition disabled:opacity-50"
              >
                {reviewSubmitting ? 'Submitting...' : 'Submit Review'}
              </button>

              {reviewSubmitMsg && (
                <p className={`text-sm text-center ${reviewSubmitMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600'}`}>
                  {reviewSubmitMsg}
                </p>
              )}
            </form>

            {/* Look up reviews */}
            <div className="bg-white/10 border border-white/20 rounded-2xl p-6 space-y-4">
              <h3 className="text-white font-bold text-sm uppercase tracking-widest">Browse Reviews</h3>
              <form onSubmit={handleLookupReviews} className="flex gap-2">
                <input
                  type="text"
                  value={reviewLookupCode}
                  onChange={e => setReviewLookupCode(e.target.value)}
                  placeholder="Enter course code (e.g. MAT237H1)"
                  className="flex-1 rounded-xl border border-white/20 bg-white/10 text-white placeholder-white/40 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-white/30 transition"
                />
                <button
                  type="submit"
                  disabled={reviewLookupLoading}
                  className="bg-white text-uoft-blue font-semibold rounded-xl px-5 py-3 text-sm hover:bg-white/90 transition disabled:opacity-50"
                >
                  Search
                </button>
              </form>

              {reviewLookupLoading && <p className="text-white/60 text-sm italic">Loading...</p>}

              {reviewResults && reviewResults.length === 0 && (
                <p className="text-white/40 text-sm italic">No reviews yet for this course.</p>
              )}

              {reviewResults && reviewResults.length > 0 && (
                <div className="space-y-3">
                  {reviewResults.map(r => (
                    <div key={r.id} className="bg-white/10 rounded-xl px-4 py-3 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-white font-semibold text-sm">{r.course_code}</span>
                        <span className="text-yellow-300 font-bold text-sm">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
                      </div>
                      {r.review_text && <p className="text-white/80 text-xs">{r.review_text}</p>}
                      <p className="text-white/40 text-xs">{new Date(r.created_at).toLocaleDateString()}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>
        )}

        </div>
      </main>
    </div>
  )
}

export default App