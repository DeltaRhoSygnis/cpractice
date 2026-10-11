A student council runs an election for class representative. Each ballot is a
single integer naming a candidate. The ballots arrive as one line of
space-separated integers: the first integer `n` is the number of ballots
(1 <= n <= 100000), and the next `n` integers are the candidate numbers that
were voted for. Candidate numbers are between 1 and 1000 inclusive.

Your job is to tally the votes and report the outcome:

- If one candidate received **strictly more than half** of all `n` ballots,
  print that candidate's number and the word `majority`, separated by a
  single space: for example `3 majority`.
- Otherwise, print the candidate who received the **most** votes, followed by
  `plurality`. If two or more candidates tie for the most votes, print the
  **smallest** such candidate number (a tie is resolved deterministically so
  the output is always well defined).

You do not need to validate the input: it is guaranteed to contain exactly
`n + 1` integers on one line, with `n` at least 1 and every ballot in range.

### Input format

One line containing n+1 space-separated integers: n, followed by n ballots.

### Output format

One line: the winning candidate number, a single space, then either
`majority` or `plurality`, followed by a newline.

### Examples

- `5 1 2 2 2 1` -> `2 majority`, because candidate 2 has 3 of 5 ballots,
  which is more than half.
- `4 7 7 9 9` -> `7 plurality`, because 7 and 9 tie on 2 votes each and the
  tie is broken toward the smaller number.
- `3 5 5 5` -> `5 majority`, because 5 has 3 of 3 ballots.
