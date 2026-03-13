# Arquitectura SPA Modular

Objetivo: robustez funcional en frontend con dominios modulares, sin microfrontends, sobre Quasar y Vite.

## Capas y responsabilidades

- `app`: bootstrap, router, providers globales y wiring transversal.
- `shared`: base HTTP, contratos compartidos, utilidades y primitives de interfaz.
- `entities`: tipos de dominio, DTOs y mapeadores API hacia interfaz.
- `features`: casos de uso por dominio, efectos de red y coordinacion con stores.
- `widgets`: composicion de flujos de interfaz sin logica de negocio compleja.
- `pages`: contenedor y orquestacion; delega a `features` y `widgets`.

## Reglas de dependencia

- `pages -> widgets/features/entities/shared`.
- `widgets -> features/entities/shared`.
- `features -> entities/shared`.
- `entities -> shared`.
- `shared` no depende de capas de dominio.

## Politica de nomenclatura visible

- Se usan nombres completos en interfaz:
- `Recursos Humanos`, `Organizacion`, `Control de Acceso`, `Roles y Permisos`, `Identidad y Acceso`, `Combustible`.
- Siglas tecnicas permitidas solo en contexto tecnico:
- `API`, `HTTP`, `CI` y codigos de permisos (`hr.*`, `org.*`, `fuel.*`).

## Navegacion canonica y compatibilidad

- Rutas canonicamente legibles:
- `/recursos-humanos/empleados`
- `/recursos-humanos/puestos`
- `/organizacion/empresas`
- `/organizacion/perfil-empresa`
- `/organizacion/sucursales`
- `/combustible`
- `/combustible/salud`
- Rutas legacy (`/hr/*`, `/org/*`, `/fuel/*`) siguen activas como alias con redireccion interna.

## Sistema visual moderno y simetrico

- Tokens globales de color, tipografia, espaciado, radio y sombras en `src/css/app.scss`.
- Tipografia base no generica: `IBM Plex Sans` para texto y `Manrope` para jerarquia.
- Layout simetrico:
- cabecera de pagina en dos zonas balanceadas (contexto y acciones),
- contenedor centrado con escala uniforme,
- tarjetas y tablas con bordes, alturas y paddings consistentes.
- Animacion sobria:
- entrada de cabecera y tarjetas con `app-fade-up`.

## Contrato de errores HTTP

- Contrato base obligatorio: `ApiErrorEnvelope`.
- Normalizador unico: `src/shared/http/api-error.ts`.
- Legacy `detail` se mantiene como fallback de compatibilidad.

## Cliente API tipado (progresivo)

- Dominio piloto inicial: Recursos Humanos y Organizacion.
- Estrategia: incorporar cliente OpenAPI por dominio y retirar DTOs manuales por lotes.
- Regla: nuevos flujos consumen tipos de `entities` antes de llegar a componentes.

## Piloto modular implementado

- `pages/HrEmployeesPage.vue` funciona como contenedor.
- `features/hr/employees/useHrEmployeesFeature.ts` concentra estado y orquestacion del flujo.
- `widgets/hr/HrEmployeesTableWidget.vue` encapsula rendering y acciones de tabla.
- Resultado: patron replicable para paginas monoliticas del resto de dominios.

## CI frontend obligatorio

- `lint`
- `typecheck`
- `unit/component tests`
- `build` de produccion

La build de produccion se mantiene como gate bloqueante.
