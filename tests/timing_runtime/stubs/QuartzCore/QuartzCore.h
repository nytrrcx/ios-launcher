#import <Foundation/Foundation.h>
#define CADisplayLink GCTestDisplayLink

typedef struct {
    float minimum;
    float maximum;
    float preferred;
} CAFrameRateRange;

@interface CADisplayLink : NSObject
@property(nonatomic) CAFrameRateRange preferredFrameRateRange;
@property(nonatomic) NSInteger preferredFramesPerSecond;
@property(nonatomic) BOOL paused;
@property(nonatomic) BOOL invalidated;
@property(nonatomic) NSUInteger rangeWrites;
@property(nonatomic) CFTimeInterval timestamp;
@end
