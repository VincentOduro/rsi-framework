# Root Cause Analyses (5-Whys)

<!-- 
When a defect is found after code was committed, perform a structured
5-Whys analysis to find the systemic root cause and create a countermeasure.

Usage:
    python3 scripts/rsi.py root-cause interactive   # Guided analysis
    python3 scripts/rsi.py root-cause list           # View all analyses

Each analysis should:
1. Ask "Why?" at least 3 times (ideally 5)
2. Each answer should explain the PREVIOUS answer
3. End with a specific, actionable countermeasure
4. Optionally create a FAIL-index entry to prevent recurrence
-->
