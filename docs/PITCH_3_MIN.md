# Three-minute pitch: acceptance-stage draft

Rehearse aloud with a timer. This script separates tested QA behavior from pending team integration. All demo examples in the repeatable walkthrough are synthetic. Earlier practice evidence must be labeled separately.

## 0:00-0:25 Problem

AI can automate personalised social-engineering conversations. But seeing a final email does not tell defenders what the system knew, why it chose an approach, or whether the reported result is true.

We are SchnitzelStrikers. Our project makes that process inspectable inside revel8's authorised AI-twin simulation. Nothing is sent to real people.

## 0:25-0:55 Solution

Our team's design connects research, strategy, writing, quality checks and response evaluation. The shared foundation now includes profiles, message formats, a model client, a simulator API client and a bare linear agent loop.

My component checks the generated work and preserves evidence. It checks sender details and approved domains, catches placeholders and simulator-directed wording, and returns clear reasons when a draft fails. A writer can correct it automatically, within a fixed retry limit.

## 0:55-1:55 Demo

[Open the offline walkthrough; identify it as synthetic.]

Here is a complete message passing. Here is an invalid draft being blocked before it reaches even our fake sender.

The correction helper returns the errors to the writer. On the second attempt, the revised message passes the final boundary. If all attempts fail, the process stops. No person approves each message.

We tested that boundary around Mavis's actual API client using fake HTTP responses. Invalid messages and pages produce zero requests. Accepted messages preserve page registration order and retry keys.

[Show the evidence report.]

The report counts one synthetic contact and one unique reply. A repeated event ID is ignored. It does not call a reply a successful incident.

## 1:55-2:30 Actual evidence and limitations

In an earlier genuine practice test, Julius's twin asked us which event we meant, who was organising it and what we wanted from him. That was one contact and a reply, with no incident recorded. It showed that a vague opening needs concrete context.

The new package has sixty-eight passing tests, including offline Chrome checks for overflow and clipping. These mechanical checks do not prove factual accuracy or award official craft points. The wrapper is ready, but the team still needs to select it in the final send paths.

## 2:30-3:00 Next and close

With another week, we would connect sourced research, stronger conversation memory and automatic visual feedback into the same loop. Today, we can demonstrate a checked draft, bounded correction and an evidence trail that keeps unknown results unknown.

Our contribution is a clear account of what the agent did, why it chose that path and what we can honestly conclude.

## Presenter notes

Only say sixty-eight tests after confirming the current verification record. The default suite skips two optional browser tests; all 68 were run successfully in the documented environment. Do not call the synthetic correction demo a live attack or a scoring result.

Use the local backup video if the demo fails. It is silent; narrate the same explanation. The earlier real practice thread is optional and remains private. Replace it with a verified scoring thread only if the team supplies one.

Two actual timed speaker rehearsals are still pending; record real durations in docs/REHEARSAL.md. Confirm the event's three-minute talk plus Q&A and final logistics with organisers.
