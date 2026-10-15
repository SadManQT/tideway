# Tideway: user study kit (3 to 5 participants, 25 minutes each)

A small user study can strengthen the interaction evidence. This kit lets the team run a small, honest study before submission and report exactly what happened. **Report only what you collected; never round up, extrapolate or invent participants.**

## Who to invite

Owners, bookkeepers or accountants of small businesses (any country). Friends and family who run a shop count; say so in the report. Aim for 3 to 5 people; record each person's role, country and business type only (no names in the report).

## Consent (read aloud, record a "yes")

> "We are students testing a prototype called Tideway for a competition. It uses made-up businesses; you will not enter any real data. We will note what you do and say, and how long tasks take. We will not record your name or face. You can stop at any time. Is that okay?"

## Setup

- `python3 run.py --db data/study-P1.sqlite3` (one database per participant).
- Sign the participant in as **Imran (accountant)** from the landing page. Stay silent while they work; if they are stuck for 60 seconds, give the hint and mark the task "assisted".

## Five tasks (start a timer for each)

| # | Task (read it as written) | Success means | Hint if stuck |
|---|---|---|---|
| T1 | "Will this business be able to pay salaries on 31 October?" | Says no, and mentions the shortfall | "Look at Cash weather." |
| T2 | "Which customer is the biggest risk to the cash?" | Names the customer from the risk answer | "Try asking Tideway." |
| T3 | "Ask Tideway something in your own language." | Gets an answer in that language | "Type in the chat box." |
| T4 | "Find a plan to fix the gap and approve it." (Sign in as Nadia for the second approval.) | Mandate issued | "Open Rescue plan." |
| T5 | "This message arrived on WhatsApp. Add it to the books." (Paste the injection sample from Inbox.) | Notices the warning and saves only the real record | "Read the red box." |

## After the tasks: System Usability Scale (1 = strongly disagree, 5 = strongly agree)

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**SUS score** = 2.5 × [(sum of odd items − 5) + (25 − sum of even items)], from 0 to 100.

Then ask: "What was most useful?", "What was confusing?", "Would you trust it to propose actions for your business? Why or why not?"

## Results template (copy into the submission)

| Participant | Role, country | T1 | T2 | T3 | T4 | T5 | SUS | Most useful | Most confusing |
|---|---|---|---|---|---|---|---|---|---|
| P1 | | ✓ / assisted / ✗, time | | | | | | | |

Also export in-app answer feedback (Assistant view, "Answer feedback") and quote it with the number of ratings. State the sample size next to every number, e.g. "4 participants; median SUS 78; 4/4 completed T4 unassisted".
