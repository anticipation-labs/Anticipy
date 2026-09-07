/** Serialize container start/erasure and persist the no-restart decision. */
export interface OwnerIdentity { id: string; legacy_uuid: string }
interface State {
  get<T>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
}
export class OwnerLifecycle {
  private queue: Promise<void> = Promise.resolve();
  private state: State;
  private exists: (ref: string) => Promise<boolean>;
  private start: (owner: OwnerIdentity) => Promise<void>;
  private kill: () => Promise<void>;

  constructor(state: State, exists: (ref: string) => Promise<boolean>,
              start: (owner: OwnerIdentity) => Promise<void>, kill: () => Promise<void>) {
    this.state = state; this.exists = exists; this.start = start; this.kill = kill;
  }

  private serial(action: () => Promise<void>): Promise<void> {
    const result = this.queue.then(action);
    this.queue = result.catch(() => {}); // a failed start must not prevent erasure
    return result;
  }

  ensure(owner: OwnerIdentity): Promise<void> {
    return this.serial(async () => {
      if (await this.state.get<boolean>("account_erased") || !await this.exists(owner.id)) {
        throw new Error("owner account is closed; refusing to start its brain");
      }
      const bound = await this.state.get<string>("owner_ref");
      if (bound && bound !== owner.id) throw new Error("container owner mismatch");
      await this.state.put("owner_ref", owner.id);
      await this.start(owner);
    });
  }

  erase(ref: string): Promise<void> {
    return this.serial(async () => {
      if (await this.exists(ref)) throw new Error("owner account is still open");
      const bound = await this.state.get<string>("owner_ref");
      if (bound && bound !== ref) throw new Error("container owner mismatch");
      // Persist before killing, so a DO restart cannot reopen the deleted
      // account. Erasure deliberately kills rather than asking Python to
      // perform a final upload of the data we are about to remove.
      await this.state.put("account_erased", true);
      await this.kill();
    });
  }
}
