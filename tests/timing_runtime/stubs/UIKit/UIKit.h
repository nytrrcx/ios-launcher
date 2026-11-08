#import <Foundation/Foundation.h>
#import <QuartzCore/QuartzCore.h>
#define UIScreen GCTestScreen

@interface UIScreen : NSObject
+ (UIScreen *)mainScreen;
@property(nonatomic) NSInteger maximumFramesPerSecond;
@end
