from dataclasses import dataclass
from math import exp

clamp           = lambda x, y, z: max(y, min(x, z))
smoid           = lambda x: 1 / (1 + exp(-x))
smoid_scaling   = lambda x: 100 * smoid(0.1 * x - 5)
half_activation = lambda x: 200 * smoid(10*(x-50)/100) * (1-smoid(10*(x-50)/100))

# Generally, the less probable an event is, the more impressive it is
# This is a rough estimate, but definitely works

@dataclass
class Factoid:
    """Superclass for interesting facts about a player"""
    interest = float("NaN")
    
    timestamp: int
    player_id: int
    battle_tag: str
    player_name: str
    
    def impressive(self):
        return self.interest * smoid_scaling(self.calc_impressive())
    
    def calc_impressive(self):
        """
        Calculate how impressive this factoid is on a scale of 0-100.
        Will be weighted by factoid type and clamped via sigmoid function
        """
        
        raise NotImplementedError()
    
    def __str__(self) -> str:
        """Convert this factoid to a human-readable string"""
        raise NotImplementedError()
    
    def __lt__(self, other):
        my_impr = self.impressive()
        other_impr = other.impressive()
        
        if my_impr == other_impr:
            # If two values are equal, use inherent interest multiplier to break ties
            return self.interest < other.interest
        else:
            # Otherwise, use clamped vals
            return my_impr < other_impr
        
    
@dataclass
class MismatchedGame(Factoid):
    """Applied when a player faces very low odds of winning"""
    interest = 0.8
    
    won:bool
    my_elo: int
    their_elo: int
    
    def calc_impressive(self):
        elo_diff = abs(self.my_elo - self.their_elo)
        
        # Convert elo to chance of me winning
        chance_to_win = 1 / (10 ** (elo_diff / 400) + 1)
        if self.my_elo > self.their_elo:
            chance_to_win = 1 - chance_to_win
    
        
        # The lower the chance of winning, the more impressive
        # Bonus if we won as the underdog too
        if chance_to_win < 0.5:
            if self.won:
                return max(0, 50 - 100 * chance_to_win) + 40 * int(chance_to_win < 0.3)
            else:
                return 0 # loss against a strong opponent is not impressive
        else:
            if not self.won and chance_to_win > 0.7:
                return 50 * chance_to_win
            else:
                return 0 # winning against a weak opponent is not impressive
        
    def __str__(self) -> str:
        # 4 cases: won vs strong opponent, won vs weak opponent, lost vs strong opponent, lost vs weak opponent
        elo_diff = abs(self.my_elo - self.their_elo)
        
        # Convert elo to chance of me winning
        chance_to_win = 1 / (10 ** (elo_diff / 400) + 1)
        if self.my_elo > self.their_elo:
            chance_to_win = 1 - chance_to_win
            
        
        if self.won:
            # We're the underdog
            if chance_to_win < 0.3:
                return f"Won against a much stronger opponent (~{int(100 * chance_to_win)}% chance to win)"
            # They're the underdog
            elif chance_to_win > 0.7:
                return f"Won against a much weaker opponent. Impressive. (~{int(100 * chance_to_win)}% chance to win)"
            else:
                return f"Won against an opponent of similar strength (~{int(100 * chance_to_win)}% chance to win)"
        else:
            # We're the underdog (and we lost)
            if  chance_to_win < 0.3:
                return f"Fought hard against much stronger opponent (~{int(100 * chance_to_win)}% chance to win)"
            # They're the underdog (and we lost)
            elif chance_to_win > 0.7:
                return f"Bungled a game against a much weaker opponent. Unfortunate. (~{int(100 * chance_to_win)}% chance to win)"
            else:
                return f"Lost against an opponent of similar strength (~{int(100 * chance_to_win)}% chance to win)"

@dataclass
class LongGame(Factoid):
    """Applied when a player plays a very long game"""
    interest = 0.6
    
    duration: int
    won: bool
    
    def calc_impressive(self):
        # The longer the game, the more impressive
        # Bonus if we won too
        duration_score = self.duration / 300 # 50 minutes = 100 score
        return duration_score + 30 * int(self.won)
    
    def __str__(self) -> str:
        # 2 cases: won vs lost
        duration_mins = self.duration // 60
        
        very = "" if duration_mins < 20 else "very "
        if self.won:
            return f"Won a {very}long game ({duration_mins} mins)"
        else:
            return f"Lost a {very}long game ({duration_mins} mins)"
    
@dataclass
class LongStreak(Factoid):
    """Applied when a player has a very long win streak"""
    interest = 0.6
    
    streak: int
    won: bool
    
    def calc_impressive(self):
        if self.streak <= 1:
            return 0
        
        return min(135, 5 * 1.4 ** self.streak * (1 + 0.5 * self.won))
    
    def __str__(self) -> str:
        # 2 cases: won vs lost
        if self.won:
            return f"Won {self.streak} games in a row"
        else:
            return f"Lost {self.streak} games in a row"

@dataclass
class EloHigh(Factoid):
    """Applied when a player's elo is very high"""
    interest = 0.9
    
    elo: int
    
    def calc_impressive(self):
        return self.elo / 500 # 5000 elo (grandmaster) = 100 score
    
    def __str__(self) -> str:
        return f"Peaked at {self.elo} elo"

@dataclass
class EloClimb(Factoid):
    """Applied when a player's elo rises"""
    interest = 0.9
    
    elo_start: int
    elo_end: int
    
    def calc_impressive(self):
        elo_diff = abs(self.elo_end - self.elo_start)
        
        # Convert elo difference to probability change
        # Using the Elo formula: 1 / (1 + 10^(-elo_diff/400))
        chance_before = 1 / (1 + 10 ** (-elo_diff/400))
        chance_diff = abs(chance_before - 0.5)
            
        # Scale to 0-100 range, noting that 400 elo = 100% chance
        return chance_diff * 300
    
    def __str__(self) -> str:
        # 2 Cases: we gained elo vs we lost elo
        elo_diff = self.elo_end - self.elo_start
        
        if elo_diff > 0:
            return f"Climbed from {self.elo_start} to {self.elo_end} elo (+{elo_diff} points)"
        else:
            return f"Dropped from {self.elo_start} to {self.elo_end} elo (-{elo_diff} points)"
    
@dataclass
class Promote(Factoid):
    """Applied when a player is promoted to a new league"""
    interest = 1
    
    league: int
    
    LEAGUE_NAMES = {
        0: "Bronze",
        1: "Silver",
        2: "Gold",
        3: "Platinum",
        4: "Diamond",
        5: "Master",
        6: "Grandmaster",
    }
    
    # Previously, there were 18 standard (apparently, counting numbers), 19 with GM
    # 5->6 should be 100
    # Lazily just use the big ones
    def calc_impressive(self):
        max_league = len(self.LEAGUE_NAMES) - 1
        return 100 * (self.league + 1) / max_league
    
    def __str__(self) -> str:
        return f"Promoted to {self.LEAGUE_NAMES[self.league]} league"

@dataclass
class SwitchRace(Factoid):
    """Applied when a player switches race"""
    interest = 0.7
    
    games_by_race: dict[str, int]
    
    def calc_impressive(self):
        # Convert to % of games played by race
        total_games = sum(self.games_by_race.values())
        if total_games == 0:
            return 0
        
        games_by_race_percent = {race: games / total_games for race, games in self.games_by_race.items()}
        
        # Find the sum of offrace games played as a percentage
        primary_race = max(games_by_race_percent, key=games_by_race_percent.get)
        games_by_race_percent.pop(primary_race)
        offrace_games = sum(games_by_race_percent.values())
        
        # The closer it is to 50%, the more impressive (note that the max possible is 50%, only counts offraces)
        return half_activation(offrace_games * 100)

    def __str__(self) -> str:
        # Drop primary race & calculate percents
        total_games = sum(self.games_by_race.values())
        if total_games == 0:
            return "Didn't play a single game"
        
        primary_race = max(self.games_by_race, key=self.games_by_race.get)
        offrace_games_by_race = {race: games for race, games in self.games_by_race.items() if race != primary_race}
        if len(offrace_games_by_race) == 0:
            return f"Played {self.games_by_race[primary_race]} games as {primary_race}"
        
        msg = "Played "
        for race, games in offrace_games_by_race.items():
            msg += f"{games} as {race} ({int(100 * games / total_games)}%), "
        msg += f"normally {primary_race}"
        return msg
    
@dataclass
class ManyGames(Factoid):
    GAMES_FOR_MAX_INTEREST = 150
    interest = 0.6
    
    games_by_race: dict[str, int]
    
    def calc_impressive(self):
        total_games = sum(self.games_by_race.values())
        if total_games == 0:
            return 0
        
        # Linearly scale from 0 to 100 on domain [0, GAMES_FOR_MAX_INTEREST]
        return 100 * clamp(total_games / self.GAMES_FOR_MAX_INTEREST, 0, 1)
    
    def __str__(self) -> str:
        total_games = sum(self.games_by_race.values())
        if total_games == 0:
            return "Didn't play a single game"

        primary_race = max(self.games_by_race, key=self.games_by_race.get)
        primary_strong = self.games_by_race[primary_race] / total_games > 0.75
        msg = f"Played a total of {total_games} games"
        if primary_strong:
            # impressive!
            if self.games_by_race[primary_race] == total_games:
                msg += f", and all of them as {primary_race}"
            else:
                msg += f", and {self.games_by_race[primary_race]} of them as {primary_race}"
        if total_games > 75:
            msg += " (wow!)"
        return msg

