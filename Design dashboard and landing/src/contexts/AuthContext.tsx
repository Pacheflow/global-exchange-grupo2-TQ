import { createContext, useContext, useState, type ReactNode } from 'react';

export type UserRole = 'visitor' | 'client' | 'admin' | 'analyst' | 'cashier';

export interface User {
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  activeClient?: string;
  clientCategory?: 'Minorista' | 'Corporativo' | 'VIP';
}

interface AuthContextValue {
  user: User | null;
  isLoggedIn: boolean;
  login: (role: UserRole) => void;
  logout: () => void;
}

const DEMO_USERS: Record<UserRole, User> = {
  visitor: { name: '', email: '', role: 'visitor' },
  client: {
    name: 'Laura Benítez',
    email: 'laura.benitez@email.com',
    role: 'client',
    activeClient: 'KNG S.A.',
    clientCategory: 'Corporativo',
  },
  admin: {
    name: 'Carlos Medina',
    email: 'carlos.medina@globalexchange.com.py',
    role: 'admin',
  },
  analyst: {
    name: 'Diego Ferreira',
    email: 'diego.ferreira@globalexchange.com.py',
    role: 'analyst',
  },
  cashier: {
    name: 'Ana González',
    email: 'ana.gonzalez@globalexchange.com.py',
    role: 'cashier',
  },
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoggedIn: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const login = (role: UserRole) => {
    if (role === 'visitor') { setUser(null); return; }
    setUser(DEMO_USERS[role]);
  };

  const logout = () => setUser(null);

  return (
    <AuthContext.Provider value={{ user, isLoggedIn: !!user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
