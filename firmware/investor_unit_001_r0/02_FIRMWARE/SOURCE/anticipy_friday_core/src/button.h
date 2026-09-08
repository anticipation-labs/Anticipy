#ifndef BUTTON_H
#define BUTTON_H

#include <stdbool.h>

typedef enum { IDLE, GRACE } FSM_STATE_T;

int button_init();
/** Consume the boot-only 3-second D7 provisioning request. */
bool button_take_provisioning_request(void);
/** Consume the boot-only 10-second D7 owner-reset request. */
bool button_take_factory_reset_request(void);
void activate_button_work();
void register_button_service();
void turnoff_all();
FSM_STATE_T get_current_button_state();

void force_button_state(FSM_STATE_T state);

#endif
