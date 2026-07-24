import { useEffect, useState } from "react";

// Small localStorage-backed string state, shared by every operator
// preference that must survive a reload (language, active view, ...).
export function usePersistedState<T extends string>(key: string, defaultValue: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => (localStorage.getItem(key) as T) || defaultValue);
  useEffect(() => { localStorage.setItem(key, value); }, [key, value]);
  return [value, setValue];
}
