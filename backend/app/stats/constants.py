"""hard-coded football-data.org identifiers we care about. these don't
change often, so it's cleaner to keep them here than to discover them
via api every time.

manchester united id (66) and competition codes are stable. if anything
changes upstream we'll know immediately because the api would 404."""

MANCHESTER_UNITED_TEAM_ID = 66

# competition codes used by football-data.org. there's a v4 endpoint
# that returns these but we hard-code for clarity and to avoid a
# bootstrap api call.
COMPETITION_CODES = {
    "premier_league": "PL",
    "champions_league": "CL",
    "europa_league": "EL",
    "fa_cup": "FAC",
    "efl_cup": "EFL",
}

# the season string we treat as 'current'. football-data uses the
# starting year of the season, so 2025-26 is "2025".
CURRENT_SEASON = "2025"