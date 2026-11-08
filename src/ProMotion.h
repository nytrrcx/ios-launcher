#import <Foundation/Foundation.h>

@interface ProMotion : NSObject
+ (NSString*)unavailableReason;
+ (BOOL)prepare:(NSError**)error;
@end
