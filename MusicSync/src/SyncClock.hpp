#pragma once
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>

namespace promotion {
// Pure decision logic: no engine calls, input handling or physics mutation.
class SyncClock {
    bool anchored = false;
    double anchorGame = 0, anchorSong = 0, previousGame = 0;
    double previousSong = 0, previousWall = 0, lastSeek = -100;
    std::optional<double> candidateSince;
    int candidateDirection = 0;

    void anchor(double game, double song, double wall) {
        anchored = true;
        anchorGame = previousGame = game;
        anchorSong = previousSong = song;
        previousWall = wall;
        candidateSince.reset();
        candidateDirection = 0;
    }
public:
    void reset() { *this = SyncClock{}; }

    // Song time is milliseconds; game and monotonic wall time are seconds.
    std::optional<uint32_t> sample(double game, double song, double wall) {
        if (!std::isfinite(game) || !std::isfinite(song) || !std::isfinite(wall) ||
            game < 0 || song < 0 || wall < 0 || song > std::numeric_limits<uint32_t>::max()) {
            reset();
            return {};
        }
        if (!anchored) { anchor(game, song, wall); return {}; }
        double gameStep = game - previousGame, songStep = song - previousSong;
        if (wall < previousWall || gameStep < -0.000001 || wall - previousWall > 5 ||
            (wall - lastSeek > 1 && (songStep < -150 || songStep - gameStep * 1000 > 750))) {
            // Retry/checkpoint, loop, manual seek, or return from suspension.
            anchor(game, song, wall);
            return {};
        }
        previousGame = game;
        previousSong = song;
        previousWall = wall;
        double expected = anchorSong + (game - anchorGame) * 1000;
        double drift = expected - song;
        if (expected < 0 || expected > std::numeric_limits<uint32_t>::max() || std::abs(drift) > 2000) {
            // An unfamiliar timeline change is not a reason to seek far away.
            anchor(game, song, wall);
            return {};
        }
        if (std::abs(drift) <= 80) { candidateSince.reset(); candidateDirection = 0; return {}; }
        int direction = drift > 0 ? 1 : -1;
        if (!candidateSince || direction != candidateDirection) {
            candidateSince = wall;
            candidateDirection = direction;
        }
        if (wall - *candidateSince < .2 || wall - lastSeek < 1) return {};
        lastSeek = wall;
        candidateSince.reset();
        return static_cast<uint32_t>(std::llround(expected));
    }
};
}
