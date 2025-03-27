import requests
from cachetools import cached, TTLCache
from Levenshtein import ratio
import time
import traceback

LAST_REQUEST_TIME = 0
TIME_BETWEEN_REQUESTS = 0.5
def wait_for_request():
    global LAST_REQUEST_TIME
    if LAST_REQUEST_TIME + TIME_BETWEEN_REQUESTS > time.monotonic():
        time.sleep(LAST_REQUEST_TIME + TIME_BETWEEN_REQUESTS - time.monotonic())
    LAST_REQUEST_TIME = time.monotonic()

def eval_search(search_term: str, query_item: dict) -> float:
    """
    Scores a single item returned from the API based on the search term.
    Uses Levenshtein ratio to give higher score to longer matches.
    """
    if not query_item: return 0
    
    members = query_item.get("members", {})
    
    # Distance from character tag (display name) to search term
    character_name = members.get("character", {}).get("tag", "")
    character_score = ratio(character_name, search_term)
    
    # Distance from battletag to search term
    battle_tag = members.get("account", {}).get("battleTag", "")
    battle_tag_score = ratio(battle_tag, search_term)
    
    # Distance from account tag (bnet name) to search term
    account_name = members.get("account", {}).get("name", "")
    account_name_score = ratio(account_name, search_term)
    
    return max(0.65 * character_score, 0.8 * battle_tag_score, 0.6 * account_name_score)

@cached(cache=TTLCache(maxsize=1024, ttl=3*24*60*60))
def search_raw(search_term: str) -> list:
    wait_for_request()
    query = requests.get(f"https://sc2pulse.nephest.com/sc2/api/character/search?term={search_term}")
    query.raise_for_status()
    return query.json()
 
def search_player(name):
    try:
        query_results = search_raw(name)
        if not query_results:
            return None
        result_scores = {eval_search(name, item): item for item in query_results}
        return result_scores[max(result_scores)]
    
    except requests.exceptions.HTTPError as e:
        print(f"Error searching for player {name}: {e}")
        traceback.print_exc()
        return None

@cached(cache=TTLCache(maxsize=1024, ttl=24*60*60))
def get_player_history(player_id):
    wait_for_request()        
    query = requests.get(f"https://sc2pulse.nephest.com/sc2/api/character/{player_id}/common?matchType=&mmrHistoryDepth=180")
    query.raise_for_status()
    return query.json()

if __name__ == "__main__":
    print(search_player("Pop101"))
    # {'leagueMax': 4, 'ratingMax': 3364, 'totalGamesPlayed': 392, 'previousStats': {'rating': 2921, 'gamesPlayed': 7, 'rank': 57897}, 'currentStats': {'rating': 3190, 'gamesPlayed': 58, 'rank': 41324}, 'members': {'protossGamesPlayed': 392, 'character': {'realm': 1, 'name': 'Pop#245', 'id': 165465170, 'accountId': 165465241, 'region': 'US', 'battlenetId': 4991826, 'tag': 'Pop', 'discriminator': 245}, 'account': {'battleTag': 'Pop101#1282', 'id': 165465241, 'partition': 'GLOBAL', 'hidden': None, 'tag': 'Pop101', 'discriminator': 1282}, 'clan': {'tag': 'dubzh', 'id': 124392, 'region': 'US', 'name': 'DAWGZ', 'members': 4, 'activeMembers': 2, 'avgRating': 2928, 'avgLeagueType': 4, 'games': 223}, 'raceGames': {'PROTOSS': 392}}}
    print(get_player_history(search_player("Pop101")["members"]["character"]["id"]))

# Schema of player history:
"""
{
  "teams": [
    {
      "rating": "number",
      "wins": "number",
      "losses": "number",
      "ties": "number",
      "id": "number",
      "legacyId": "string",
      "divisionId": "number",
      "season": "number",
      "region": "string",
      "league": {
        "type": "number",
        "queueType": "number",
        "teamType": "number"
      },
      "tierType": "number",
      "globalRank": "number",
      "regionRank": "number",
      "leagueRank": "number",
      "lastPlayed": "string (ISO date)",
      "joined": "string (ISO date)",
      "primaryDataUpdated": "string (ISO date)",
      "members": [
        {
          "protossGamesPlayed": "number",
          "character": {
            "realm": "number",
            "name": "string",
            "id": "number",
            "accountId": "number",
            "region": "string",
            "battlenetId": "number",
            "tag": "string",
            "discriminator": "number"
          },
          "account": {
            "battleTag": "string",
            "id": "number",
            "partition": "string",
            "hidden": "null | boolean",
            "tag": "string",
            "discriminator": "number"
          },
          "clan": {
            "tag": "string",
            "id": "number",
            "region": "string",
            "name": "string",
            "members": "number",
            "activeMembers": "number",
            "avgRating": "number",
            "avgLeagueType": "number",
            "games": "number"
          },
          "raceGames": {
            "PROTOSS": "number"
          }
        }
      ],
      "globalTeamCount": "number",
      "regionTeamCount": "number",
      "leagueTeamCount": "number",
      "leagueType": "number",
      "queueType": "number",
      "teamType": "number",
      "legacyUid": "string"
    }
  ],
  "linkedDistinctCharacters": [
    {
      "leagueMax": "number",
      "ratingMax": "number",
      "totalGamesPlayed": "number",
      "previousStats": {
        "rating": "number",
        "gamesPlayed": "number",
        "rank": "number"
      },
      "currentStats": {
        "rating": "number",
        "gamesPlayed": "number",
        "rank": "number"
      },
      "members": {
        "protossGamesPlayed": "number",
        "character": {
          "realm": "number",
          "name": "string",
          "id": "number",
          "accountId": "number",
          "region": "string",
          "battlenetId": "number",
          "tag": "string",
          "discriminator": "number"
        },
        "account": {
          "battleTag": "string",
          "id": "number",
          "partition": "string",
          "hidden": "null | boolean",
          "tag": "string",
          "discriminator": "number"
        },
        "clan": {
          "tag": "string",
          "id": "number",
          "region": "string",
          "name": "string",
          "members": "number",
          "activeMembers": "number",
          "avgRating": "number",
          "avgLeagueType": "number",
          "games": "number"
        },
        "raceGames": {
          "PROTOSS": "number"
        }
      }
    }
  ],
  "stats": [
    {
      "stats": {
        "id": "number",
        "playerCharacterId": "number",
        "queueType": "number",
        "teamType": "number",
        "race": "string | null",
        "ratingMax": "number",
        "leagueMax": "number",
        "gamesPlayed": "number"
      },
      "previousStats": {
        "rating": "number | null",
        "gamesPlayed": "number | null",
        "rank": "number | null"
      },
      "currentStats": {
        "rating": "number | null",
        "gamesPlayed": "number | null",
        "rank": "number | null"
      }
    }
  ],
  "matches": [
    {
      "match": {
        "date": "string (ISO date)",
        "type": "string",
        "id": "number",
        "mapId": "number",
        "region": "string",
        "updated": "string (ISO date)",
        "duration": "number | null"
      },
      "map": {
        "id": "number",
        "name": "string"
      },
      "participants": [
        {
          "participant": {
            "matchId": "number",
            "playerCharacterId": "number",
            "teamId": "number | null",
            "teamStateDateTime": "string (ISO date) | null",
            "decision": "string",
            "ratingChange": "number | null"
          },
          "team": "object | null",
          "teamState": "object | null",
          "twitchVodUrl": "string | null",
          "subOnlyTwitchVod": "boolean | null"
        }
      ]
    }
  ],
  "history": {
    "teamId": "number[]",
    "race": "string[]",
    "dateTime": "string[] (ISO date)",
    "leagueRank": "number[]",
    "games": "number[]",
    "rating": "number[]",
    "teamType": "number[]",
    "regionTeamCount": "number[]",
    "leagueType": "number[]",
    "wins": "number[]",
    "leagueTeamCount": "number[]",
    "queueType": "number[]",
    "globalRank": "number[]",
    "season": "number[]",
    "tier": "number[]",
    "regionRank": "number[]",
    "globalTeamCount": "number[]"
  },
  "reports": "array"
}
"""