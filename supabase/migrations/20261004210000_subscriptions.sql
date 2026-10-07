-- One Stripe subscription per user, written only by the backend's webhook
-- and checkout handlers. Stripe is the source of truth; this is its mirror.
create table if not exists public.subscriptions (
  user_id uuid primary key references auth.users(id) on delete cascade,
  stripe_customer_id text not null unique,
  stripe_subscription_id text,
  status text not null default 'none',
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  updated_at timestamptz not null default now()
);

alter table public.subscriptions enable row level security;

create policy "Users can read their subscription"
  on public.subscriptions for select
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can create their subscription"
  on public.subscriptions for insert
  to nfinit_backend
  with check ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can update their subscription"
  on public.subscriptions for update
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id)
  with check ((select public.nfinit_request_user_id()) = user_id);

revoke all on public.subscriptions from anon, authenticated;
grant select, insert, update on public.subscriptions to nfinit_backend;
