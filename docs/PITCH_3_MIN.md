# Three-minute pitch: speaker script and demo cues

Draft for rehearsal, about three minutes at a measured pace. This script distinguishes main's implementation from earlier TRACE practice evidence. Replace practice with an actual scoring thread only after one exists. Do not claim the package is wired into every sender yet.

## 0:00-0:30 Problem

Imagine receiving an email that understands your role and responds naturally when you ask questions. AI makes personalised social engineering easier to automate. Seeing the final email is not enough: defenders need to understand how the system chose an approach, what the recipient did, and whether the evidence supports the claimed result.

We are SchnitzelStrikers, and our project makes those decisions inspectable.

## 0:30-1:10 System and quality

Our team's design connects research, strategy, writing, quality checks and response evaluation. The current shared foundation includes typed profiles, messages and decision trees, a common model client, and practice tools for revel8's authorised AI twins.

My component checks the generated work. It accepts the team's shared message format, checks the sender and approved domains, catches unfinished placeholders and simulator-directed instructions, and returns structured reasons when something fails.

A bounded correction helper lets the writer try again automatically. If it still fails, it stops. It does not ask a human to approve each message. The adapter is ready; connecting it to every final send remains an integration task.

## 1:10-2:05 Genuine practice example

[Open the locally saved practice thread, clearly labeled earlier TRACE practice evidence.]

In a real practice interaction from our earlier TRACE prototype, the agent offered an event outline to Julius's AI twin. Julius asked which event it was, who was organising it, and what we wanted from him.

That is one contact and an actual reply, not a successful incident. It tells us the opening lacked concrete context. We preserve the distinction instead of counting engagement as a win.

We also render emails and pages offline at the judging widths. The earlier email exposed another craft issue: it had no sender identity recorded. Our new final-message adapter requires one.

## 2:05-2:40 Evidence and architecture

Our results adapter reads the current tree files and terminal chat logs. It removes duplicate event IDs and counts a call once rather than once per sentence. Where the source contains only a written outcome note, it does not invent API events or a touch count.

[Show the implemented architecture and one PASS/BLOCK preview.]

The local tests exercise the shared schemas, automatic retry limit, blocked content and reporting boundaries. Official outcomes, hidden topic hits and craft scores remain unknown unless supported by authoritative evidence.

## 2:40-3:00 Close

The next step is integrating sourced research, richer writing and the quality boundary into one autonomous loop. Our contribution is a record of what actually happened, why a path was chosen, and what we can honestly conclude from it.

That makes the agent's behaviour understandable to both defenders and judges.

## Rehearsal and evidence rules

- Time the spoken script including clicks twice. Record actual duration; never mark a human rehearsal complete from a word-count estimate.
- Use local saved practice evidence if the network is slow. A fresh clone contains no private run data.
- The local backup clip is an offline demonstration, not a scored run, live call or narrated rehearsal.
- Keep the current-main implementation separate from earlier TRACE practice provenance.
- Confirm three-minute talk plus Q&A with organisers. Sunday 22 November: stated submission window 12:00-12:45, aim to finish at 12:40, Europe/Berlin.
- No official incident, scoring success or completed submission is claimed in this script.
