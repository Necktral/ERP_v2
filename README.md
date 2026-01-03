
# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría, HR, ORG, IAM, sincronización y ciclo de arranque profesional con Docker Compose.

## Backend: ciclo de arranque recomendado

### 1. Clona el repositorio y configura variables
```bash
git clone https://github.com/Necktral/Necktral.git
cd ERP_CRM
cp .env.example .env  # Edita los valores según tu entorno
```

### 2. Levanta los servicios con Docker Compose
```bash
docker compose up -d --force-recreate
```

### 3. Aplica migraciones y crea el superusuario admin
```bash
docker compose exec backend python src/manage.py migrate --noinput
docker compose exec backend python src/manage.py createsuperuser --username admin --email admin@example.com --noinput
```

### 4. Siembra RBAC y bootstrap de empresa/sucursal/admin
```bash
docker compose exec backend python src/manage.py seed_rbac_v01
docker compose exec backend python src/manage.py bootstrap_company \
	--no-input \
	--holding-name HOLDING \
	--company-name ACME \
	--company-code AC \
	--branch-name ACME-1 \
	--branch-code AC1 \
	--admin-username admin
```

### 5. Accede al backend
El backend queda expuesto en http://localhost:8000

### 6. Variables de entorno principales (.env)
Revisa y ajusta:
- DB_NAME, DB_USER, DB_PASSWORD: credenciales de Postgres
- DJANGO_SECRET_KEY: clave secreta Django
- DJANGO_ALLOWED_HOSTS: hosts permitidos
- DJANGO_CORS_ALLOWED_ORIGINS: orígenes frontend permitidos

### 7. Flujo de desarrollo frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Comandos útiles
- `docker compose logs backend --tail=60` — Ver logs del backend
- `docker compose exec backend python src/manage.py showmigrations` — Ver estado de migraciones
- `docker compose exec db psql -U <DB_USER> -d <DB_NAME> -c "\\l"` — Ver bases de datos en Postgres

---

## Documentación extendida
Consulta el archivo login_module/README.md para detalles de endpoints, comandos, ciclo de migraciones, auditoría y buenas prácticas.

---

Actualizado al 2026-01-03.
