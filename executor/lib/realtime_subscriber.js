// Supabase Realtime subscriber — listens on the per-user channel
// `task.dispatched.{user_id}` for new rows in anticipy_tasks_v2 and
// invokes a handler.
//
// Per the migration, anticipy_tasks_v2 is in the supabase_realtime
// publication, so INSERTs broadcast automatically. The subscriber filters
// by user_id to avoid cross-user leakage on the shared topic.

const { createClient } = require('@supabase/supabase-js');

class RealtimeSubscriber {
  constructor({ supabaseUrl, supabaseServiceKey, userId }) {
    this.userId = userId;
    this.client = createClient(supabaseUrl, supabaseServiceKey, {
      realtime: { params: { eventsPerSecond: 10 } },
    });
    this._channel = null;
    this._handlers = [];
  }

  onTask(handler) {
    this._handlers.push(handler);
    return this;
  }

  start() {
    if (this._channel) return this;
    const channelName = `task.dispatched.${this.userId}`;
    this._channel = this.client
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'anticipy_tasks_v2',
          filter: `user_id=eq.${this.userId}`,
        },
        (payload) => {
          const row = payload?.new;
          if (!row) return;
          for (const h of this._handlers) {
            try {
              h(row);
            } catch (e) {
              console.error('[realtime] task handler threw:', e);
            }
          }
        }
      )
      .subscribe((status, err) => {
        if (err) console.error('[realtime] subscribe error:', err);
        else console.log('[realtime]', channelName, 'status:', status);
      });
    return this;
  }

  async stop() {
    if (this._channel) {
      await this.client.removeChannel(this._channel);
      this._channel = null;
    }
  }
}

module.exports = { RealtimeSubscriber };
