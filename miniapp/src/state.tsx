import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, setClubId } from "./api";
import type { AuthMe, Membership, Role } from "./types";

interface AppState {
  me: AuthMe | null;
  loading: boolean;
  error: string | null;
  activeClub: Membership | null;
  role: Role | null;
  selectClub: (clubId: number) => void;
  reload: () => Promise<void>;
}

const AppContext = createContext<AppState>({} as AppState);
export const useApp = () => useContext(AppContext);

const LAST_CLUB_KEY = "fc_last_club";

export function AppProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<AuthMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeClub, setActiveClub] = useState<Membership | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<AuthMe>("/auth/me", { clubScoped: false });
      setMe(data);
      if (data.clubs.length > 0) {
        const lastId = Number(localStorage.getItem(LAST_CLUB_KEY) || 0);
        const chosen =
          data.clubs.find((c) => c.club.id === lastId) ?? data.clubs[0];
        setActiveClub(chosen);
        setClubId(chosen.club.id);
      } else {
        setActiveClub(null);
        setClubId(null);
      }
    } catch (e: any) {
      setError(e?.message ?? "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectClub(clubId: number) {
    const m = me?.clubs.find((c) => c.club.id === clubId) ?? null;
    setActiveClub(m);
    setClubId(m ? m.club.id : null);
    if (m) localStorage.setItem(LAST_CLUB_KEY, String(clubId));
  }

  return (
    <AppContext.Provider
      value={{
        me,
        loading,
        error,
        activeClub,
        role: activeClub?.role ?? null,
        selectClub,
        reload: load,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// Role helper mirroring the backend hierarchy.
const WEIGHT: Record<Role, number> = {
  trainer: 10,
  club_admin: 20,
  club_owner: 30,
  platform_admin: 100,
};
export function atLeast(role: Role | null, min: Role): boolean {
  if (!role) return false;
  return WEIGHT[role] >= WEIGHT[min];
}
