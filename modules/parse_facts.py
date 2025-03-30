from modules.factoids import MismatchedGame, LongGame, LongStreak, EloHigh, Promote, SwitchRace, ManyGames, EloClimb
from modules.search_player import search_player, get_player_history
from modules.traverse import traverse
from dateutil.parser import parse
from itertools import zip_longest
import datetime
import re
from collections import Counter

def parse_player_history(player, history, cutoff_date:datetime.datetime = datetime.datetime(year=1, month=1, day=1, tzinfo=datetime.timezone.utc)):
    """Parses all match history for a player and yields all interesting facts"""
    
    player_id = player["members"]["character"]["id"]
    battle_tag = player["members"]["account"]["battleTag"]
    player_name = re.match(r"^(.*?)#", player["members"]["character"]["name"]).group(1)
    
    # The rest of the events must come from history. Let's put it into a parseable format
    HISTORY_KEYS = ['teamId', # nonsense
                    'race', # race played by this player
                    'dateTime', # datetime of game
                    'leagueRank', # rank in the league
                    'games', # culmulative count of games played of this queueType
                    'teamType', # nonsense (always 0?)
                    'leagueType', # 0 is bronze, etc...
                    'wins', # culmulative count of wins of this queueType
                    'leagueTeamCount',
                    'queueType', # 201 is autoMM
                    'globalRank', # rank in the world
                    'season', # season of game
                    'regionRank', # rank in the region (NA) <-- most useful
                    'globalTeamCount' # nonsense
                    ]
    
    # history['history'] has one entry for each key in HISTORY_KEYS
    # we want to convert this to a list of dicts, where each dict has the keys as keys, and the values as values
    all_hist = []
    history['history']['dateTime'] = [parse(date) for date in history['history']['dateTime']]
    values = [history['history'].get(key, []) for key in HISTORY_KEYS]
    for entry in zip_longest(*values, fillvalue=None):
        hist_dict = {key: value for key, value in zip(HISTORY_KEYS, entry)}
        if hist_dict['race'] is not None:
            hist_dict['race'] = hist_dict['race'].lower()
        if hist_dict['dateTime'] < cutoff_date:
            continue
        if hist_dict['queueType'] != 201:
            continue
        
        all_hist.append(hist_dict)
    
    if len(all_hist) == 0:
        return
    
    # Event 1: Offracing
    race_counts        = Counter(hist_dict['race'] for hist_dict in all_hist)
    yield SwitchRace(
        timestamp   = max(history['history']['dateTime']),
        player_id   = player_id,
        player_name = player_name,
        battle_tag  = battle_tag,
        
        games_by_race = race_counts,
    )
    
    # Event 2: Many Games
    yield ManyGames(
        timestamp   = max(history['history']['dateTime']),
        player_id   = player_id,
        player_name = player_name,
        battle_tag  = battle_tag,

        games_by_race = race_counts,
    )

def parse_player_matches(player, matches, cutoff_date:datetime.datetime = datetime.datetime(year=1, month=1, day=1, tzinfo=datetime.timezone.utc)):
    """Parses match-by-match history for a player and yields all interesting facts"""
    # This code is very hard to read...
    
    player_id   = player["members"]["character"]["id"]
    battle_tag  = player["members"]["account"]["battleTag"]
    player_name = re.match(r"^(.*?)#", player["members"]["character"]["name"]).group(1)
    
    streak_count = 0
    streak_won   = True
    
    highest_elo          = 0
    lowest_elo           = 0
    highest_after_lowest = None
    
    max_league      = None
    league_switches = 0
    
    # We need to reverse-calculate this to get the elo for every match
    current_elo          = player["currentStats"]["rating"] # NONE
    for match in matches:
        # Decypher the match: who am I and who is my opponent?
        if len(match["participants"]) != 2: continue
        
        team_zero = match["participants"][0]
        team_one = match["participants"][1]
        
        if traverse(team_zero, 'team', 'members') is None: continue
        if traverse(team_one, 'team', 'members') is None : continue
        
        # Ignore games before cutoff date
        if parse(match["match"]["date"]) < cutoff_date:
            continue
        
        # For now: ignore all non-1v1s
        # Very hard to compare 1v1s to team games and arcade
        if match["match"]["type"] != "_1V1":
            continue
        
        if any(x['character']['id'] == player_id for x in team_zero["team"]["members"]):
            my_team    = team_zero
            other_team = team_one
        else: 
            my_team    = team_one
            other_team = team_zero
        
        # Update Stats
        won           = my_team["participant"]["decision"] == "WIN"
        curr_division = my_team["team"]["league"]["type"]
        elo           = my_team["team"]["rating"]
        
        if highest_after_lowest == None:
            highest_elo = elo
            lowest_elo = elo
            highest_after_lowest = True
            
        if elo > highest_elo:
            highest_after_lowest = True
            highest_elo = elo
            
        elif elo < lowest_elo:
            highest_after_lowest = False
            lowest_elo = elo
        
        # Update current elo (if we won, the current elo of the past is less than the current elo now)
        if my_team["participant"]["ratingChange"] is not None:
            if won:
                current_elo -= my_team["participant"]["ratingChange"]
            else:
                current_elo += my_team["participant"]["ratingChange"]
        
        # Event 0: Promote?
        if max_league == None:
            max_league = curr_division
        elif curr_division > max_league:
            league_switches += 1
            max_league = curr_division
            
            yield Promote(
                timestamp   = parse(match["match"]["date"]),
                player_id   = player_id,
                player_name = player_name,
                battle_tag  = battle_tag,
                
                league = max_league,
            )
        
        # Event 1: Possible Mismatch?
        if traverse(other_team, 'team', 'rating') is not None:
            yield MismatchedGame(
                timestamp   = parse(match["match"]["date"]),
                player_id   = player_id,
                player_name = player_name,
                battle_tag  = battle_tag,
                
                my_elo    = current_elo,                  #my_team["team"]["rating"] would be logical, but is too often null,
                their_elo = other_team["team"]["rating"],
                won       = won,
            )
        
        # Event 2: Long Game?
        if traverse(match, 'duration') is not None:
            yield LongGame(
                timestamp   = parse(match["match"]["date"]),
                player_id   = player_id,
                player_name = player_name,
                battle_tag  = battle_tag,
                
                duration = match["duration"],
            )
        
        # Event 2: Streak?
        if won:
            if streak_won:
                streak_count += 1
            else:
                yield LongStreak(
                    timestamp   = parse(match["match"]["date"]),
                    player_id   = player_id,
                    player_name = player_name,
                    battle_tag  = battle_tag,
                    
                    streak = streak_count,
                    won    = True,
                )
                
                streak_count = 1
                streak_won   = True
                
        else:
            if not streak_won:
                streak_count += 1
            else:
                yield LongStreak(
                    timestamp   = parse(match["match"]["date"]),
                    player_id   = player_id,
                    player_name = player_name,
                    battle_tag  = battle_tag,
                    
                    streak = streak_count,
                    won    = False,
                )
                
                streak_count = 1
                streak_won   = False
    
    # Clean up streak data
    if streak_count > 0: 
        yield LongStreak(
            timestamp   = parse(match["match"]["date"]),
            player_id   = player_id,
            player_name = player_name,
            battle_tag  = battle_tag,

            streak = streak_count,
            won    = streak_won,
        )
        
    if 'match' in locals(): 
    #  Event 3            : Elo Peak
        yield EloHigh(
            timestamp   = parse(match["match"]["date"]),
            player_id   = player_id,
            player_name = player_name,
            battle_tag  = battle_tag,
            
            elo = highest_elo,
        )
        
        # Event 4: Elo Climb
        yield EloClimb(
            timestamp   = parse(match["match"]["date"]),
            player_id   = player_id,
            player_name = player_name,
            battle_tag  = battle_tag,

            elo_start = lowest_elo if highest_after_lowest else highest_elo,
            elo_end   = highest_elo if highest_after_lowest else lowest_elo,
        )
        
        

def parse_player_facts(search_term, cutoff_date:datetime.datetime = datetime.datetime(year=1, month=1, day=1, tzinfo=datetime.timezone.utc)):
    # TODO: a lot of info we'd like to rely on is null
    
    player = search_player(search_term)
    if not player:
        return
    
    player_id = player["members"]["character"]["id"]
    battle_tag = player["members"]["account"]["battleTag"]
    player_name = re.match(r"^(.*?)#", player["members"]["character"]["name"]).group(1)
    history = get_player_history(player_id)
    
    for fact in parse_player_matches(player, history['matches'], cutoff_date=cutoff_date):
        yield fact
        
    for fact in parse_player_history(player, history, cutoff_date=cutoff_date):
        yield fact

if __name__ == "__main__":
    for i, event in enumerate(sorted(list(parse_player_facts("Pop101")), reverse=True)):
        print(f"event {i}: {event}")
        print(f"score={event.impressive()},\traw_score={event.calc_impressive()}")
        print()
        print()
    