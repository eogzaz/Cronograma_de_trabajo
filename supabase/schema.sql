-- ============================================================================
-- Esquema Supabase — Sistema de Gestión para Despacho Contable
-- ============================================================================
-- Pensado para reemplazar utils/mock_data.py 1:1 (ver utils/db.py).
-- Ejecutar en el SQL Editor de Supabase, en orden (respeta las FKs).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- EQUIPO (contadores / auxiliares del despacho)
-- ---------------------------------------------------------------------------
create table equipo (
    id           bigint generated always as identity primary key,
    nombre       text not null,
    rol          text not null,              -- 'Contador Senior', 'Contadora', 'Auxiliar Contable', ...
    email        text unique,                -- para vincular con Supabase Auth más adelante
    auth_user_id uuid references auth.users (id),
    creado_en    timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- CLIENTES
-- ---------------------------------------------------------------------------
create table clientes (
    id                    bigint generated always as identity primary key,
    nombre                text not null,
    nit                   text not null unique,
    responsable_id        bigint references equipo (id) on delete set null,
    estado                text not null default 'Activo' check (estado in ('Activo', 'Inactivo')),
    proximo_vencimiento   text,               -- etiqueta libre, p.ej. "IVA julio"
    fecha_vencimiento     date,
    creado_en             timestamptz not null default now()
);

create index idx_clientes_fecha_vencimiento on clientes (fecha_vencimiento);
create index idx_clientes_responsable on clientes (responsable_id);

-- ---------------------------------------------------------------------------
-- TAREAS
-- ---------------------------------------------------------------------------
create table tareas (
    id              bigint generated always as identity primary key,
    titulo          text not null,
    cliente_id      bigint references clientes (id) on delete cascade,
    responsable_id  bigint references equipo (id) on delete set null,
    estado          text not null default 'Pendiente'
                        check (estado in ('Pendiente', 'En proceso', 'Finalizada', 'Vencida')),
    prioridad       text not null default 'Media' check (prioridad in ('Baja', 'Media', 'Alta')),
    fecha_limite    date,
    creado_en       timestamptz not null default now(),
    actualizado_en  timestamptz not null default now()
);

create index idx_tareas_estado on tareas (estado);
create index idx_tareas_responsable on tareas (responsable_id);
create index idx_tareas_cliente on tareas (cliente_id);

-- Historial de eventos de una tarea (reemplaza get_historial_tarea)
create table tarea_historial (
    id        bigint generated always as identity primary key,
    tarea_id  bigint not null references tareas (id) on delete cascade,
    evento    text not null,
    creado_en timestamptz not null default now()
);

create index idx_tarea_historial_tarea on tarea_historial (tarea_id);

-- ---------------------------------------------------------------------------
-- CHECKLISTS
-- ---------------------------------------------------------------------------
-- Plantilla: los pasos fijos por tipo de obligación (IVA, Retención, Renta, Nómina...)
create table checklist_template_items (
    id       bigint generated always as identity primary key,
    tipo     text not null,               -- 'IVA', 'Retención', 'Renta', 'Nómina'
    orden    int not null,
    paso     text not null,
    unique (tipo, orden)
);

-- Progreso real por cliente + tipo de obligación (reemplaza session_state)
create table checklist_items (
    id               bigint generated always as identity primary key,
    cliente_id       bigint not null references clientes (id) on delete cascade,
    tipo             text not null,
    template_item_id bigint not null references checklist_template_items (id),
    completado       boolean not null default false,
    tarea_id         bigint references tareas (id) on delete set null,
    actualizado_en   timestamptz not null default now(),
    unique (cliente_id, template_item_id)
);

create index idx_checklist_items_cliente_tipo on checklist_items (cliente_id, tipo);

-- ---------------------------------------------------------------------------
-- DOCUMENTOS (metadatos; los binarios viven en Supabase Storage)
-- ---------------------------------------------------------------------------
create table documentos (
    id             bigint generated always as identity primary key,
    cliente_id     bigint not null references clientes (id) on delete cascade,
    nombre_archivo text not null,
    storage_path   text not null,          -- ruta dentro del bucket de Storage
    subido_por     bigint references equipo (id) on delete set null,
    creado_en      timestamptz not null default now()
);

create index idx_documentos_cliente on documentos (cliente_id);

-- ---------------------------------------------------------------------------
-- SEED de checklist_template_items (equivalente a get_checklist_template)
-- ---------------------------------------------------------------------------
insert into checklist_template_items (tipo, orden, paso) values
    ('IVA', 1, 'Solicitar documentos'),
    ('IVA', 2, 'Revisar compras'),
    ('IVA', 3, 'Revisar ventas'),
    ('IVA', 4, 'Conciliar'),
    ('IVA', 5, 'Elaborar declaración'),
    ('IVA', 6, 'Revisar'),
    ('IVA', 7, 'Presentar'),
    ('IVA', 8, 'Enviar soporte'),
    ('Retención', 1, 'Solicitar certificados'),
    ('Retención', 2, 'Revisar bases'),
    ('Retención', 3, 'Calcular retenciones'),
    ('Retención', 4, 'Elaborar declaración'),
    ('Retención', 5, 'Presentar'),
    ('Retención', 6, 'Enviar soporte'),
    ('Renta', 1, 'Solicitar estados financieros'),
    ('Renta', 2, 'Conciliar patrimonio'),
    ('Renta', 3, 'Depurar renta'),
    ('Renta', 4, 'Elaborar declaración'),
    ('Renta', 5, 'Revisar'),
    ('Renta', 6, 'Presentar'),
    ('Renta', 7, 'Enviar soporte'),
    ('Nómina', 1, 'Recibir novedades'),
    ('Nómina', 2, 'Calcular nómina'),
    ('Nómina', 3, 'Calcular seguridad social'),
    ('Nómina', 4, 'Generar comprobantes'),
    ('Nómina', 5, 'Pagar seguridad social'),
    ('Nómina', 6, 'Enviar soportes');

-- ---------------------------------------------------------------------------
-- ROW LEVEL SECURITY (habilitado por defecto; ajusta las políticas a tu caso)
-- ---------------------------------------------------------------------------
-- Por ahora se deja una política abierta a usuarios autenticados para poder
-- desarrollar rápido. Antes de producción, restringe por auth_user_id / rol.
alter table equipo enable row level security;
alter table clientes enable row level security;
alter table tareas enable row level security;
alter table tarea_historial enable row level security;
alter table checklist_template_items enable row level security;
alter table checklist_items enable row level security;
alter table documentos enable row level security;

create policy "Usuarios autenticados pueden leer/escribir" on equipo
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy "Usuarios autenticados pueden leer/escribir" on clientes
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy "Usuarios autenticados pueden leer/escribir" on tareas
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy "Usuarios autenticados pueden leer/escribir" on tarea_historial
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy "Lectura pública de plantillas" on checklist_template_items
    for select using (true);
create policy "Usuarios autenticados pueden leer/escribir" on checklist_items
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy "Usuarios autenticados pueden leer/escribir" on documentos
    for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
