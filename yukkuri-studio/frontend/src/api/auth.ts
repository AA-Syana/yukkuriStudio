import type { User } from "../types";
import { http } from "./client";

export const authApi = {
  me: () => http.get<User>("/auth/me"),
  login: (email: string, password: string) => http.post<User>("/auth/login", { email, password }),
  register: (email: string, password: string) => http.post<User>("/auth/register", { email, password }),
  logout: () => http.post<void>("/auth/logout", {}),
};
