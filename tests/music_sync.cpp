#include "../MusicSync/src/SyncClock.hpp"
#include <cstdlib>
#include <iostream>
#include <string>

static void check(bool value, const char* message) {
    if (!value) { std::cerr << message << '\n'; std::exit(1); }
}

int main(int argc, char** argv) {
    check(argc == 2, "select a test");
    std::string test = argv[1];
    promotion::SyncClock clock;
    if (test == "long-ahead" || test == "long-behind" || test == "no-drift" || test == "variable-fps") {
        double game = 0, song = 9000, wall = 10, nextPoll = wall;
        double rate = test == "long-ahead" ? 1.001 : test == "long-behind" ? .999 : 1;
        int corrections = 0;
        clock.sample(game, song, wall);
        for (int frame = 0; frame < 120 * 20 * 60; ++frame) {
            double step = test == "variable-fps" && frame % 37 == 0 ? 1.0 / 30 : 1.0 / 120;
            wall += step;
            game += step * rate;
            song += step * 1000;
            if (wall < nextPoll) continue;
            nextPoll = wall + .1;
            if (auto target = clock.sample(game, song, wall)) {
                song = *target;
                corrections++;
            }
            check(std::abs(song - (9000 + game * 1000)) < 85, "long-running drift stays bounded");
        }
        check((rate == 1 && corrections == 0) || (rate != 1 && corrections >= 10), "correct only persistent drift");
    } else if (test == "offset") {
        clock.sample(500, 130000, 10);
        for (int i = 1; i <= 100; ++i)
            check(!clock.sample(500 + i * .1, 130000 + i * 100, 10 + i * .1), "preserve nonzero starting offset");
    } else if (test == "transient") {
        clock.sample(1, 1000, 1);
        check(!clock.sample(1.1, 1005, 1.1), "brief stale FMOD reading is not corrected immediately");
        check(!clock.sample(1.2, 1200, 1.2), "transient clears");
        check(!clock.sample(1.3, 1205, 1.3), "new transient starts a new timer");
        check(!clock.sample(1.4, 1400, 1.4), "second transient clears");
    } else if (test == "cooldown") {
        clock.sample(0, 1000, 0);
        clock.sample(1, 1900, 1);
        check(clock.sample(1.3, 2200, 1.3).has_value(), "persistent drift corrects");
        check(!clock.sample(1.5, 2400, 1.5), "unacknowledged seek does not trigger another immediately");
        check(!clock.sample(2, 2900, 2), "limit seeks to at most once per second");
        check(clock.sample(2.4, 3300, 2.4).has_value(), "failed seek may retry after cooldown");
    } else if (test == "alternating-jitter") {
        clock.sample(0, 1000, 0);
        for (int i = 1; i <= 100; ++i) {
            double error = i % 2 ? 90 : -90;
            check(!clock.sample(i * .1, 1000 + i * 100 - error, i * .1), "alternating jitter is not persistent drift");
        }
    } else if (test == "restart") {
        clock.sample(50, 52000, 5);
        check(!clock.sample(.1, 2100, 5.1), "retry establishes new baseline");
        check(!clock.sample(.2, 2200, 5.2), "retry preserves new song start offset");
        clock.reset();
        check(!clock.sample(120, 90000, 50), "pause/checkpoint reset accepts new timeline");
    } else if (test == "manual-seek") {
        clock.sample(50, 50000, 10);
        check(!clock.sample(50.1, 80000, 10.1), "external forward seek accepted");
        check(!clock.sample(50.2, 80100, 10.2), "do not undo manual seek");
        check(!clock.sample(50.3, 100, 10.3), "song loop or backward seek accepted");
        check(!clock.sample(50.4, 200, 10.4), "loop baseline preserved");
    } else if (test == "invalid") {
        for (double invalid : {double(NAN), double(INFINITY), -1.0}) {
            check(!clock.sample(invalid, 100, 1), "invalid game clock rejected");
            check(!clock.sample(1, invalid, 1), "invalid song clock rejected");
        }
        check(!clock.sample(1, 100, NAN), "invalid wall clock rejected");
        check(!clock.sample(1, 1e20, 1), "out-of-range song position rejected");
        clock.sample(0, 1000, 0);
        check(!clock.sample(10, 1100, 1), "large discontinuity reanchors instead of seeking seconds away");
    } else if (test == "suspension") {
        clock.sample(10, 10000, 10);
        check(!clock.sample(10.1, 10100, 50), "return from suspension reanchors");
        check(!clock.sample(10.2, 10200, 50.1), "no correction after suspension");
        check(!clock.sample(10.3, 10300, 40), "backward wall-clock change reanchors");
    } else { check(false, "unknown test"); }
    std::cout << "PASS: " << test << '\n';
}
