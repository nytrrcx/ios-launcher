#include <Geode/Geode.hpp>
#include <Geode/modify/PlayLayer.hpp>
#include <chrono>
#include <cstddef>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include "SyncClock.hpp"

using namespace geode::prelude;

// Verify the SDK layouts against the native instructions in the supplied
// GD 2.208 / SDK 2.2081 game before packaging any code that reads these fields.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Winvalid-offsetof"
static_assert(offsetof(GJBaseGameLayer, m_gameState) + offsetof(GJGameState, m_levelTime) == 0x3a0);
static_assert(offsetof(GJBaseGameLayer, m_gameState) + offsetof(GJGameState, m_timeWarp) == 0x330);
static_assert(offsetof(FMODAudioEngine, m_fmodMusic) == 0x140);
#pragma clang diagnostic pop

static bool promotionEnabled() {
    const char* value = std::getenv("ANGLEGLKit");
    return value && !std::strcmp(value, "1");
}

class $modify(ProMotionMusicSyncLayer, PlayLayer) {
    struct Fields {
        promotion::SyncClock clock;
        bool ready = false;
        bool audioTriggers = false;
        double nextPoll = 0;
    };

    bool init(GJGameLevel* level, bool replay, bool dontCreateObjects) {
        m_fields->ready = false;
        if (!PlayLayer::init(level, replay, dontCreateObjects)) return false;
        // Audio triggers define their own seeks, loops, rates and channels.
        // Leave those authored timelines to the game instead of guessing.
        m_fields->audioTriggers = !m_objects;
        if (m_objects) {
            for (auto* object : CCArrayExt<GameObject*>(m_objects)) {
                if (typeinfo_cast<SFXTriggerGameObject*>(object)) {
                    m_fields->audioTriggers = true;
                    break;
                }
            }
        }
        m_fields->clock.reset();
        m_fields->nextPoll = 0;
        m_fields->ready = true;
        if (promotionEnabled()) {
            log::info("ProMotion Music Sync: {}. CBF/input/physics settings are unchanged.",
                      m_fields->audioTriggers ? "audio-trigger level excluded" : "main-song drift monitor ready");
        }
        return true;
    }

    void postUpdate(float dt) {
        // Preserve the game's and other mods' original callback exactly once.
        PlayLayer::postUpdate(dt);
        auto& state = *m_fields.operator->();
        if (!state.ready || state.audioTriggers || !promotionEnabled() ||
            !Mod::get()->getSettingValue<bool>("enabled") || !m_started ||
            m_isPaused || m_playerDied || m_hasCompletedLevel || m_inResetDelay ||
            (m_isPracticeMode && !m_practiceMusicSync) || m_isPlatformer || !m_player1 ||
            !std::isfinite(m_gameState.m_timeWarp) || std::abs(m_gameState.m_timeWarp - 1.0f) > .0001f) {
            state.clock.reset();
            state.nextPoll = 0;
            return;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        if (wall < state.nextPoll) return;
        state.nextPoll = wall + .1;

        auto* audio = FMODAudioEngine::sharedEngine();
        if (!audio || audio->m_allAudioPaused || !audio->m_fmodMusic.contains(0) ||
            audio->m_fmodMusic.size() != 1 || !audio->isMusicPlaying(0)) {
            state.clock.reset();
            return;
        }
        for (auto const& [channel, pitch] : audio->m_audioState.m_pitchForMusicChannels) {
            if (!std::isfinite(pitch) || std::abs(pitch - 1.0f) > .0001f) {
                state.clock.reset();
                return;
            }
        }
        auto position = audio->getMusicTimeMS(0);
        if (!position) { state.clock.reset(); return; } // Wait for stream start.
        auto target = state.clock.sample(m_gameState.m_levelTime, position, wall);
        if (!target) return;
        auto length = audio->getMusicLengthMS(0);
        if (length && *target >= length) { state.clock.reset(); return; }
        // The native music-ID API selects the main song, not master-channel 0
        // (which could be a sound effect). Do not wait for stream loading.
        audio->setMusicTimeMS(*target, true, 0);
        log::info("ProMotion Music Sync: song corrected by {} ms at level time {:.3f} s",
                  static_cast<int64_t>(*target) - position, m_gameState.m_levelTime);
    }

    void resetLevel() {
        m_fields->clock.reset();
        m_fields->nextPoll = 0;
        PlayLayer::resetLevel();
    }
};
