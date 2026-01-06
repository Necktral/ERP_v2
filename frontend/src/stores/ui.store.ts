import { defineStore } from 'pinia';
import {
  readUiPrefs,
  writeUiPrefs,
  type UiDensityMode,
  type UiThemeMode,
} from 'src/core/storage/ui';

export const useUiStore = defineStore('ui', {
  state: () => ({
    hydrated: false as boolean,
    theme: 'light' as UiThemeMode,
    density: 'comfortable' as UiDensityMode,
  }),

  actions: {
    initFromStorage() {
      if (this.hydrated) return;
      const prefs = readUiPrefs();
      this.theme = prefs.theme;
      this.density = prefs.density;
      this.hydrated = true;
    },

    setTheme(theme: UiThemeMode) {
      this.theme = theme;
      writeUiPrefs({ theme: this.theme, density: this.density });
    },

    setDensity(density: UiDensityMode) {
      this.density = density;
      writeUiPrefs({ theme: this.theme, density: this.density });
    },
  },
});
