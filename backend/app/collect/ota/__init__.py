"""OTA fare scrapers (Cleartrip, EaseMyTrip).

A faithful port of the scraping logic proven in
`ankit70808/Airfare-Price-Index`, refactored so the *parsing* is pure data
in/out (testable offline against captured HTML/JSON) and the *browser* is only
touched by the adapter / CLI layers. Each site returns the same canonical
payload shape the rest of the collection engine consumes, so scraped fares flow
through normalize -> quality gate -> store -> index -> API unchanged.
"""
