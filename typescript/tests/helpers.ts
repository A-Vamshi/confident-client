import axios from "axios";

import {
  CONFIDENT_BASE_URL_ENV_VAR,
  CONFIDENT_ORG_API_KEY_ENV_VAR,
  CONFIDENT_PROJ_API_KEY_ENV_VAR,
  CONFIDENT_REGION_ENV_VAR,
} from "../src/api";

jest.mock("axios");

export const mockedAxios = axios as unknown as jest.Mock;

export interface RecordedCall {
  method: string;
  url: string;
  headers: Record<string, string>;
  params?: Record<string, unknown>;
  data?: unknown;
}

/** Queue a successful `{ success, data }` envelope response. */
export function mockData(data: unknown, status = 200): void {
  mockedAxios.mockResolvedValueOnce({ status, data: { success: true, data } });
}

/** Queue a raw response body with an explicit status. */
export function mockRaw(body: unknown, status = 200): void {
  mockedAxios.mockResolvedValueOnce({ status, data: body });
}

/** The config object passed to the most recent axios call. */
export function lastCall(): RecordedCall {
  const calls = mockedAxios.mock.calls;
  return calls[calls.length - 1][0] as RecordedCall;
}

export function resetAxios(): void {
  mockedAxios.mockReset();
}

/** Remove every Confident AI environment variable. */
export function clearConfidentEnv(): void {
  for (const envVar of [
    CONFIDENT_ORG_API_KEY_ENV_VAR,
    CONFIDENT_PROJ_API_KEY_ENV_VAR,
    CONFIDENT_BASE_URL_ENV_VAR,
    CONFIDENT_REGION_ENV_VAR,
  ]) {
    delete process.env[envVar];
  }
}
