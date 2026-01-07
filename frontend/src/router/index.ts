import { route } from 'quasar/wrappers';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import routes from './routes';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

export default route(function () {
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : process.env.VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory;

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(process.env.VUE_ROUTER_BASE),
  });

  Router.beforeEach(async (to) => {
    const auth = useAuthStore();
    const acl = useAclStore();
    const ctx = useContextStore();

    auth.initFromStorage();
    ctx.initFromStorage();

    // Ensure user details are loaded if authenticated
    if (auth.isAuthenticated && !auth.user) {
      await auth.fetchMe();
    }

    // --- Onboarding / Bootstrap Logic ---

    // 0) Unauthenticated: Check for system freshness (First run)
    if (!auth.isAuthenticated) {
      // Only check if we are not already going there and haven't checked recently
      // Ideally we check this once per app load.
      // We can check if we are heading to login.
      if (to.path === '/login' || to.path === '/') {
        await auth.checkBootstrap();
        if (auth.bootstrapState.is_fresh) {
          return { path: '/bootstrap' };
        }
      }
    }

    // 0.5) Authenticated: Security & Setup checks
    if (auth.isAuthenticated) {
      // Enforce password change
      if (auth.user?.must_change_password) {
        if (to.path !== '/password-change' && to.path !== '/logout') {
          return { path: '/password-change' };
        }
      }

      // Enforce setup completion (if user has no companies or explicit flag)
      // We need ACL loaded to know companies.
      if (acl.loaded) {
        // ACL is loaded in step 2 usually, but we check here if loaded
        if (auth.user?.is_setup_complete === false) {
          if (!to.path.startsWith('/bootstrap') && to.path !== '/logout') {
            return { path: '/bootstrap' };
          }
        }
      }
    }

    const requiresAuth = Boolean(to.meta?.requiresAuth);
    const requiresContext = Boolean(to.meta?.requiresContext);

    // 1) Si requiere auth y no hay sesión → login
    if (requiresAuth && !auth.isAuthenticated) {
      if (to.path !== '/login') return { path: '/login' };
      return true;
    }

    // 2) Si hay sesión y ACL no está cargado, cargarlo
    if (auth.isAuthenticated && !acl.loaded) {
      try {
        await acl.loadAcl();
      } catch {
        // Si no podemos cargar ACL, forzamos logout
        await auth.logout();
        return { path: '/login' };
      }
    }

    // 3) Si tenemos ACL y no hay contexto, intentar autoselección si el ACL lo recomienda
    if (auth.isAuthenticated && acl.loaded && !ctx.activeCompanyId) {
      const recCompany = acl.recommendedCompanyId;
      const recBranch = acl.recommendedBranchId;

      if (recCompany) ctx.setContext(recCompany, recBranch ?? null);
    }

    // 4) Si la ruta requiere contexto y no hay company → select-context
    if (requiresContext && !ctx.activeCompanyId) {
      if (to.path !== '/select-context') return { path: '/select-context' };
      return true;
    }

    const required = to.meta?.requiredPermissions as string[] | undefined;
    if (required && required.length > 0) {
      const companyId = ctx.activeCompanyId;
      if (!companyId) return { path: '/select-context' };

      const ok = required.every((p) => acl.hasPermission(companyId, p));
      if (!ok) return { path: '/403' };
    }

    return true;
  });

  return Router;
});
