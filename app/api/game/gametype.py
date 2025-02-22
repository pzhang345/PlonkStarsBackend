from models import GameType
from api.game.games.challenge import ChallengeGame
from api.game.games.live import LiveGame

game_type = {
    GameType.CHALLENGE: ChallengeGame(),
    GameType.LIVE: LiveGame()
}