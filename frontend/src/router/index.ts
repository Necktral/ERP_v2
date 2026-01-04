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

    return true;
  });

  return Router;
});
