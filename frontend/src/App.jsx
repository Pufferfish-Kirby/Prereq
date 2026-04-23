import { useState, useRef, useEffect } from 'react'
import './App.css'

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
  // Which tab is active: 'planner' (the existing form) or 'chat'
  const [activeTab, setActiveTab] = useState('planner')

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

  // Ref to the bottom of the message list — we scroll to it after each new message
  // so the user always sees the latest response without manually scrolling.
  const messagesEndRef = useRef(null)
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, chatLoading])

  async function handleChatSend(e) {
    e.preventDefault()
    const text = inputValue.trim()
    if (!text || chatLoading) return

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
        }),
      })

      if (!response.ok) throw new Error(`Server error: ${response.status}`)

      const data = await response.json()
      setMessages([...updatedHistory, { role: 'assistant', content: data.response }])
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

  return (
    // Full-height dark-blue background — this is UofT's primary brand colour (#002A5C)
    <div className="min-h-screen bg-uoft-blue flex flex-col">

      {/* ── Navbar ── */}
      <header className="bg-uoft-blue border-b border-white/20 px-8 py-4 flex items-center gap-3">
        <div className="w-1 h-8 bg-white rounded-full" />
        <h1 className="text-white text-xl font-semibold tracking-wide">MyUofT</h1>
        <span className="text-white/50 text-sm ml-1">/ Course Planner</span>

        {/* Tab switcher in the navbar — right-aligned */}
        <div className="ml-auto flex gap-1 bg-white/10 rounded-lg p-1">
          {['planner', 'chat'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`
                px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-all
                ${activeTab === tab
                  ? 'bg-white text-uoft-blue shadow'
                  : 'text-white/70 hover:text-white'}
              `}
            >
              {tab === 'chat' ? 'AI Advisor' : 'Course Planner'}
            </button>
          ))}
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-8">

        {/* ══════════════════════════════════════════
            CHAT TAB
            A scrollable message history + input bar.
            Shown when activeTab === 'chat'.
        ══════════════════════════════════════════ */}
        {activeTab === 'chat' && (
          <div className="flex flex-col h-[70vh]">
            <div className="text-center mb-6">
              <h2 className="text-white text-3xl font-bold tracking-tight">AI Advisor</h2>
              <p className="text-white/60 mt-2 text-sm">
                Ask anything about UofT courses, programs, or degree requirements.
              </p>
            </div>

            {/* Scrollable message list */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 mb-4">
              {messages.length === 0 && (
                <p className="text-white/40 text-sm text-center mt-8 italic">
                  No messages yet — say hello!
                </p>
              )}

              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`
                      max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed
                      ${msg.role === 'user'
                        ? 'bg-white text-uoft-blue rounded-br-sm'
                        : 'bg-white/15 text-white rounded-bl-sm'}
                    `}
                  >
                    {msg.content}
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

              {chatError && (
                <p className="text-red-300 text-xs text-center">{chatError}</p>
              )}

              {/* Invisible anchor we scroll into view after each message */}
              <div ref={messagesEndRef} />
            </div>

            {/* Input bar */}
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
        )}

        {/* ══════════════════════════════════════════
            PLANNER TAB — existing form, unchanged
        ══════════════════════════════════════════ */}
        {activeTab === 'planner' && (<>

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
          <form
            onSubmit={handleSubmit}
            className="bg-white rounded-2xl shadow-xl p-8 space-y-6"
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
                      className="bg-white/10 border border-white/20 rounded-xl px-4 py-3 flex items-start gap-4"
                    >
                      <div className="shrink-0 w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                        <span className="text-white text-xs font-bold">{course.score}</span>
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
        </>)}
        {/* end activeTab === 'planner' */}

        </div>
      </main>
    </div>
  )
}

export default App