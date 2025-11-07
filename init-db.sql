create table if not exists public.instances (
  id uuid primary key,
  status text not null,
  container_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.qr_codes (
  id uuid primary key,
  instance_id uuid references public.instances(id) on delete cascade,
  qr_string text not null,
  created_at timestamptz not null default now()
);

create index if not exists qr_codes_instance_id_idx on public.qr_codes(instance_id, created_at desc);
