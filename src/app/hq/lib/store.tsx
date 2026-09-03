"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { AGENT_RUNS, EVENTS, NOTIFICATIONS, PEOPLE, TASKS } from "./data";
import type {
  AgentRun,
  CalendarEvent,
  HQNotification,
  Person,
  PersonId,
  Task,
} from "./types";

interface HQState {
  user: PersonId | null;
  unlocked: boolean;
  walkthroughDone: boolean;
  tasks: Task[];
  runs: AgentRun[];
  events: CalendarEvent[];
  notifications: HQNotification[];
  people: Person[];
  setUnlocked: (v: boolean) => void;
  setUser: (u: PersonId | null) => void;
  setWalkthroughDone: (v: boolean) => void;
  updateTask: (id: string, patch: Partial<Task>) => void;
  addTask: (task: Task) => void;
  updateRun: (id: string, patch: Partial<AgentRun>) => void;
  addRun: (run: AgentRun) => void;
  addEvent: (ev: CalendarEvent) => void;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
  logActivity: (taskId: string, text: string) => void;
}

const HQContext = createContext<HQState | null>(null);

const LS_KEY = "anticipy-hq-session";

export function HQProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<PersonId | null>(null);
  const [unlocked, setUnlockedState] = useState(false);
  const [walkthroughDone, setWalkthroughDoneState] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const [tasks, setTasks] = useState<Task[]>(TASKS);
  const [runs, setRuns] = useState<AgentRun[]>(AGENT_RUNS);
  const [events, setEvents] = useState<CalendarEvent[]>(EVENTS);
  const [notifications, setNotifications] = useState<HQNotification[]>(NOTIFICATIONS);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const s = JSON.parse(raw);
        if (s.unlocked) setUnlockedState(true);
        if (s.user) setUserState(s.user);
        setWalkthroughDoneState(Boolean(s.walkthroughDone));
      } else {
        setWalkthroughDoneState(false);
      }
    } catch {
      setWalkthroughDoneState(false);
    }
    setHydrated(true);
  }, []);

  const persist = useCallback(
    (patch: Record<string, unknown>) => {
      try {
        const raw = localStorage.getItem(LS_KEY);
        const s = raw ? JSON.parse(raw) : {};
        localStorage.setItem(LS_KEY, JSON.stringify({ ...s, ...patch }));
      } catch {
        /* prototype: ignore storage failures */
      }
    },
    []
  );

  const setUnlocked = useCallback((v: boolean) => {
    setUnlockedState(v);
    persist({ unlocked: v });
  }, [persist]);

  const setUser = useCallback((u: PersonId | null) => {
    setUserState(u);
    persist({ user: u });
  }, [persist]);

  const setWalkthroughDone = useCallback((v: boolean) => {
    setWalkthroughDoneState(v);
    persist({ walkthroughDone: v });
  }, [persist]);

  const updateTask = useCallback((id: string, patch: Partial<Task>) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  const addTask = useCallback((task: Task) => {
    setTasks((prev) => [task, ...prev]);
  }, []);

  const updateRun = useCallback((id: string, patch: Partial<AgentRun>) => {
    setRuns((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const addRun = useCallback((run: AgentRun) => {
    setRuns((prev) => [run, ...prev]);
  }, []);

  const addEvent = useCallback((ev: CalendarEvent) => {
    setEvents((prev) => [...prev, ev]);
  }, []);

  const markNotificationRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  const markAllNotificationsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const logActivity = useCallback((taskId: string, text: string) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId
          ? {
              ...t,
              activity: [
                ...t.activity,
                { id: `act-${Date.now()}`, text, at: new Date().toISOString() },
              ],
            }
          : t
      )
    );
  }, []);

  const value = useMemo<HQState>(
    () => ({
      user,
      unlocked,
      walkthroughDone,
      tasks,
      runs,
      events,
      notifications,
      people: PEOPLE,
      setUnlocked,
      setUser,
      setWalkthroughDone,
      updateTask,
      addTask,
      updateRun,
      addRun,
      addEvent,
      markNotificationRead,
      markAllNotificationsRead,
      logActivity,
    }),
    [
      user, unlocked, walkthroughDone, tasks, runs, events, notifications,
      setUnlocked, setUser, setWalkthroughDone, updateTask, addTask, updateRun,
      addRun, addEvent, markNotificationRead, markAllNotificationsRead, logActivity,
    ]
  );

  if (!hydrated) {
    return <div style={{ minHeight: "100vh", background: "#FFFFFF" }} />;
  }

  return <HQContext.Provider value={value}>{children}</HQContext.Provider>;
}

export function useHQ(): HQState {
  const ctx = useContext(HQContext);
  if (!ctx) throw new Error("useHQ must be used inside HQProvider");
  return ctx;
}
