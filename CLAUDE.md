# ERP_v2 — Instrucciones para Claude Code

Sistema de trabajo para avanzar **en orden, por grupos, sin dejar nada en el camino**.
Trabaja siempre con `ROADMAP.md` (la lista viva de tareas) a la par de este archivo.

## 1. Orden: jerarquía de ensamblaje
Todo se prioriza por las **CAPAS** de `ROADMAP.md`:
**Capa 0 Consolidar → 1 Ciclo nómina → 2 Datos reales → 3 Anti-fraude → 4 Columna económica → 5 Frontend/móvil → 6 Módulos futuros.**
No se sube de capa sin **cerrar** la anterior, o sin que el usuario decida explícitamente saltarla.

## 2. Unidad de trabajo: el GRUPO activo
- Hay **UN solo grupo `[DOING]`** a la vez (un slice de una capa, p.ej. "U4 — nómina→GL").
- Dentro del grupo, las tareas se hacen **en orden** y se commitea **una por tarea** (commits atómicos y verdes).
- **No se empieza un grupo nuevo sin confirmación del usuario.**

## 3. Flujo por sesión (obligatorio)
**Al iniciar:**
1. Leer `ROADMAP.md` + memoria. Identificar el grupo `[DOING]`. Si no hay, **proponer** el siguiente según la jerarquía y **CONFIRMAR** antes de arrancar.

**Durante:**
2. Ejecutar solo los ítems del grupo activo.
3. Cada ítem terminado: **tests verdes → commit descriptivo → marcar `[DONE]`** en `ROADMAP.md`.
4. **No dejar nada en el camino:** todo lo roto/faltante que se descubra FUERA del scope se anota de inmediato como `[TODO]` en `ROADMAP.md` (en su capa). NO se arregla ahora.

**Al cerrar (o al cambiar de grupo):**
5. Actualizar `ROADMAP.md` (estados + log de sesión) y la memoria.
6. Reportar qué se hizo y cuál es el próximo `[DOING]` sugerido. **Detenerse.**

## 4. Git y aislamiento (lección aprendida)
- Trabajo de feature → en **git worktree aislado** (carpeta aparte) para **NO colisionar** con el árbol principal, donde el usuario hace merges/saneamiento en paralelo.
- Higiene OBLIGATORIA: `git add` con **rutas explícitas** + revisar `git diff --cached --stat`. **Nunca `git add .`.** Excluir `excel/` y `*:Zone.Identifier`.
- **No push ni merge a master** sin pedido/confirmación del usuario.

## 5. Prohibido sin permiso explícito
- Refactorizar o arreglar lints/warnings **fuera del scope** del grupo activo (anotarlo como `[TODO]`).
- Cambiar archivos fuera del grupo `[DOING]`.
- Empezar el siguiente grupo sin confirmación.
- Commits con tests rojos.

## 6. Definición de DONE (por ítem)
- [ ] Tests del ítem verdes; suite del módulo sin regresión.
- [ ] `makemigrations --check` sin cambios pendientes (o la migración va incluida).
- [ ] `ruff` limpio en lo tocado.
- [ ] Commit hecho con mensaje descriptivo.
- [ ] `ROADMAP.md` actualizado.

## 7. Stack y ejecución
- Django 5.2 + DRF + PostgreSQL; tests con pytest-django.
- Settings de test: `config.settings.test`; PYTHONPATH y código en `backend/src`.
- Migraciones: `makemigrations` antes de `migrate`; nunca editar una migración aplicada.
- Correr en Docker (runbook en memoria): contenedor backend, slot de DB único; one-off con
  `--entrypoint bash` para saltar el setup del entrypoint.
