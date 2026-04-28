# Section 2 — Error & Rescue Map template

This is the output table format for Phase 2 Section 2 (Error & Rescue Map).
Read this file just before walking Section 2.

The map has **two paired tables**:

1. **Failure-mode table** — for each new method / codepath, list every
   distinct way it can fail and the exception class that names that failure.
2. **Rescue table** — for each exception class, document whether it's
   rescued, the rescue action, and what the user sees.

A rescued failure with no specific exception class is a smell. A failure
that is logged but not communicated to the user is usually a smell. A
catch-all (`catch Exception`) is always a smell.

---

## Failure-mode table

```
METHOD / CODEPATH        | WHAT CAN GO WRONG           | EXCEPTION CLASS
-------------------------|-----------------------------|-----------------
ExampleService.call()    | API timeout                 | TimeoutError
                         | API returns 429             | RateLimitError
                         | API returns malformed JSON  | JSONParseError
                         | DB connection pool exhausted| ConnectionPoolExhausted
                         | Record not found            | RecordNotFound
-------------------------|-----------------------------|-----------------
```

For each new method / codepath added by the plan:

- List **every distinct failure mode** — not "API failure" but the specific
  reason (timeout vs. 4xx vs. 5xx vs. malformed body vs. transport error).
- Use **specific exception classes**. If the language / framework doesn't
  have one, name a new one and propose it as a code change. Generic
  `Error` / `Exception` / `RuntimeError` is not acceptable.
- LLM / AI service calls have at least four failure modes: malformed,
  empty, hallucinated invalid JSON, model refusal. Each is distinct.

---

## Rescue table

```
EXCEPTION CLASS              | RESCUED? | RESCUE ACTION          | USER SEES
-----------------------------|----------|------------------------|------------------
TimeoutError                 | Y        | Retry 2×, then raise   | "Service unavailable"
RateLimitError               | Y        | Backoff + retry        | Nothing (transparent)
JSONParseError               | N <- GAP | -                      | 500 error <- BAD
ConnectionPoolExhausted      | N <- GAP | -                      | 500 error <- BAD
RecordNotFound               | Y        | Return nil, log warning| "Not found" message
-----------------------------|----------|------------------------|------------------
```

For each exception class from the failure-mode table:

- **Rescued?** — Y / N. If N, the row is a GAP (mark with `<- GAP`).
- **Rescue action** — what code does. Specific verbs: "retry 2× with
  exponential backoff", "return cached value", "fall back to v1 endpoint",
  "re-raise with added context (request ID + timestamp)". "Log and continue"
  is almost never acceptable.
- **User sees** — concrete user-visible outcome. "Service unavailable"
  banner / "Saved locally, will sync later" / silent transparent retry /
  HTTP 500 response. If the user sees a generic 500, mark `<- BAD` —
  every 500 the user sees is a missed rescue.

### Rescue action rules

Each rescued error must take one of three forms:

1. **Retry with backoff** — define max retries and the backoff curve. Don't
   retry indefinitely. Don't retry on errors that won't change (4xx aside
   from 408 / 429).
2. **Degrade gracefully with user-visible message** — the user knows
   something went wrong AND has a path forward (retry button, "saved
   locally", "try again later").
3. **Re-raise with added context** — the error continues up, but with the
   surrounding state attached (input arguments, user / request ID, timestamp,
   correlation ID). Never swallow.

"Swallow and continue" — log the error and continue as if nothing happened —
is almost never acceptable. Surface it as a Section 2 issue.

---

## Required outputs from Section 2

After populating both tables:

1. The **failure-mode table** as a fenced code block in the review note.
2. The **rescue table** as a fenced code block, with GAP rows highlighted.
3. A **gap-summary** paragraph: count of GAP rows, count flagged BAD,
   one-sentence severity ranking. Critical rule: any GAP that has no test
   AND no error handling AND would be silent is a **CRITICAL GAP** — flag
   it in capital letters.
4. **Rescue-action recommendations** for each GAP. Each issue is its own
   AskUserQuestion call, presenting the recommended rescue + alternatives.

---

## Worked example (cart review-request submission)

```
METHOD / CODEPATH                      | WHAT CAN GO WRONG          | EXCEPTION CLASS
---------------------------------------|----------------------------|------------------
ReviewService.submitReview(orderId,*)  | Network timeout            | NetworkTimeoutError
                                       | 401 from review API        | UnauthorizedError
                                       | 429 rate-limited           | RateLimitError
                                       | 5xx (transient)            | UpstreamError
                                       | Malformed response body    | ResponseDecodingError
                                       | orderId already submitted  | DuplicateSubmissionError
                                       | Local DB write fails       | LocalPersistenceError
---------------------------------------|----------------------------|------------------

EXCEPTION CLASS               | RESCUED? | RESCUE ACTION                  | USER SEES
------------------------------|----------|--------------------------------|---------------------
NetworkTimeoutError           | Y        | Retry 2× w/ jittered backoff   | "Saved locally, syncing"
UnauthorizedError             | Y        | Refresh token, retry once      | Silent if refresh OK
RateLimitError                | Y        | Honor Retry-After, max 1 retry | "Try again in {N}s"
UpstreamError                 | Y        | Local persist + bg retry       | "Saved locally, syncing"
ResponseDecodingError         | N <- GAP | -                              | 500 error <- BAD
DuplicateSubmissionError      | Y        | Treat as success (idempotent)  | Success state
LocalPersistenceError         | N <- GAP | -                              | Silent loss <- CRITICAL GAP
------------------------------|----------|--------------------------------|---------------------

Gap summary: 2 GAPs. 1 CRITICAL (LocalPersistenceError causes silent data
loss). Severity: address LocalPersistenceError before merge; address
ResponseDecodingError before any GA.

Rescue recommendations:
2A. ResponseDecodingError → emit a structured event + user-visible "Could not
    confirm submission, please retry" toast. (Section 2)
2B. LocalPersistenceError → escalate to Sentry + display "Failed to save
    locally — your review wasn't sent" banner. Block submit-button until
    persistence works. (Section 2 — CRITICAL)
```

---

## Common failures in Section 2

| Failure | Symptom | Fix |
|---------|---------|-----|
| "Catches all exceptions, logs, continues" | Hides real failures forever | Demand specific exception classes per branch |
| "We'll add error handling later" | Implementation never gets it | Add error handling as part of the plan, not after |
| "It's just a transient error, the next call will succeed" | Glosses over chronic-vs-transient | Distinguish: transient = retry; chronic = surface |
| "Empty response means no data" | Conflates empty with error | Distinguish 200-with-empty-body vs. error response |
| "We log it, the user sees a 500" | Logging is not user communication | Replace 500 with structured user message |
