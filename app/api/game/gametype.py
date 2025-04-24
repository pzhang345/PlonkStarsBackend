from models.session import GameType
from api.game.games.challenge import ChallengeGame
from api.game.games.live import LiveGame

game_type = {
    GameType.CHALLENGE: ChallengeGame(),
    GameType.LIVE: LiveGame(),
}

str_to_type = {
    "challenge":GameType.CHALLENGE,
}

str_to_type_socket = {
    "live": GameType.LIVE
}


