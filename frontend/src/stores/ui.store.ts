import { defineStore } from 'pinia';
import {
  readUiPrefs,
  writeUiPrefs,
  type UiDensityMode,
  type UiThemeMode,
} from 'src/core/storage/ui';

interface UiState {
  hydrated: boolean;
  theme: UiThemeMode;
  density: UiDensityMode;
}

export const useUiStore = defineStore('ui', {
  state: (): UiState => ({
    hydrated: false,
    theme: 'light',
    density: 'comfortable',
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
