from api.game.games.duels import DuelsGame
from api.game.games.challenge import ChallengeGame
from api.game.games.live import LiveGame

from models.session import GameType

game_type = {
    GameType.CHALLENGE: ChallengeGame(),
    GameType.LIVE: LiveGame(),
    GameType.DUELS: DuelsGame()
}

str_to_type = {
    "challenge":GameType.CHALLENGE,
}

str_to_type_socket = {
    "live": GameType.LIVE,
    "duels": GameType.DUELS
}
