#import "AudioTapExceptionShield.h"

@implementation AudioTapExceptionShield

+ (BOOL)perform:(NS_NOESCAPE void (^)(void))operation {
    @try {
        operation();
        return YES;
    } @catch (__unused NSException *exception) {
        return NO;
    }
}

@end
