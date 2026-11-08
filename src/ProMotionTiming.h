#import <Foundation/Foundation.h>

// Install a diagnostic observer after loading the game, before entering main().
// GameTimingMachO configures the actual frame timer before signing.
BOOL GCInstallGameProMotionTiming(NSString **error);
