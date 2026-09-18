export type Role = "platform_admin" | "club_owner" | "club_admin" | "trainer";

export interface User {
  id: number;
  telegram_id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language: string;
  is_platform_admin: boolean;
}

export interface Club {
  id: number;
  name: string;
  timezone: string;
  currency: string;
  default_language: string;
  is_active: boolean;
  notify_expiry_enabled: boolean;
  notify_overdue_enabled: boolean;
  notify_daily_summary_enabled: boolean;
  expiry_reminder_days: number;
  created_at: string;
}

export interface Membership {
  club: Club;
  role: Role;
}

export interface AuthMe {
  user: User;
  clubs: Membership[];
}

export interface Client {
  id: number;
  first_name: string;
  last_name?: string;
  phone?: string;
  birth_date?: string;
  note?: string;
  status: "active" | "archived";
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Plan {
  id: number;
  name: string;
  price: number;
  duration_value: number;
  duration_unit: "days" | "months";
  visit_limit?: number | null;
  description?: string;
  is_active: boolean;
  created_at: string;
}

export interface Subscription {
  id: number;
  client_id: number;
  plan_id: number;
  start_date: string;
  end_date: string;
  status: string;
  visit_limit?: number | null;
  visits_used: number;
  price: number;
  frozen_days: number;
  created_at: string;
}

export interface Payment {
  id: number;
  client_id: number;
  amount: number;
  method: "cash" | "card" | "transfer" | "other";
  comment?: string;
  paid_at: string;
  is_reversed: boolean;
  created_at: string;
}

export interface Ledger {
  client_id: number;
  total_charged: number;
  total_paid: number;
  total_discount: number;
  total_correction: number;
  balance: number;
  debt: number;
  credit: number;
}

export interface DebtRow {
  client_id: number;
  client_name: string;
  debt: number;
}

export interface Dashboard {
  active_clients: number;
  visits_today: number;
  subscriptions_ending_soon: number;
  clients_with_debt: number;
  total_debt: number;
  income_in_period: number;
  period_start: string;
  period_end: string;
}

export interface VisitEligibility {
  allowed: boolean;
  reason: string;
  subscription_id?: number | null;
  status?: string | null;
  visits_left?: number | null;
}

export interface Visit {
  id: number;
  client_id: number;
  subscription_id?: number | null;
  result: string;
  override_reason?: string;
  note?: string;
  created_at: string;
}

export interface Staff {
  membership_id: number;
  user: User;
  role: Role;
  is_active: boolean;
}

export interface Invite {
  id: number;
  code: string;
  role: Role;
  telegram_id?: number | null;
  status: string;
  expires_at: string;
  created_at: string;
}
