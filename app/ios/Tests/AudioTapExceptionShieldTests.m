#import <Foundation/Foundation.h>
#import "../Anticipy/Audio/AudioTapExceptionShield.h"

int main(void) {
    @autoreleasepool {
        __block BOOL completed = NO;
        BOOL normal = [AudioTapExceptionShield perform:^{
            completed = YES;
        }];
        if (!normal || !completed) {
            NSLog(@"the exception shield did not complete an ordinary operation");
            return 1;
        }

        BOOL raised = [AudioTapExceptionShield perform:^{
            [NSException raise:@"AudioTapTestException" format:@"route changed"];
        }];
        if (raised) {
            NSLog(@"the exception shield reported a thrown operation as successful");
            return 1;
        }

        NSLog(@"audio tap exception shield: ordinary calls pass and NSException becomes failure");
    }
    return 0;
}
