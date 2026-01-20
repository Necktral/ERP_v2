import { api } from 'src/boot/axios';

export type FuelHealth = {
  ok: boolean;
  module: string;
};

export async function getFuelHealth() {
  const { data } = await api.get<FuelHealth>('/fuel/health/');
  return data;
}
